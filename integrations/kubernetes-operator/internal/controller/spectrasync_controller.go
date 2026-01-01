// Copyright (c) spectra
// SPDX-License-Identifier: MIT

package controller

import (
	"context"
	"fmt"
	"time"

	"github.com/robfig/cron/v3"
	batchv1 "k8s.io/api/batch/v1"
	corev1 "k8s.io/api/core/v1"
	"k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/client-go/tools/record"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	"sigs.k8s.io/controller-runtime/pkg/log"

	spectrav1alpha1 "github.com/spectra/spectra/integrations/kubernetes-operator/api/v1alpha1"
)

const (
	spectraSyncFinalizer = "spectra.io/finalizer"
)

// SpectraSyncReconciler reconciles a SpectraSync object
type SpectraSyncReconciler struct {
	client.Client
	Scheme       *runtime.Scheme
	Recorder     record.EventRecorder
	SpectraImage string
}

// +kubebuilder:rbac:groups=spectra.io,resources=spectrasyncs,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=spectra.io,resources=spectrasyncs/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=spectra.io,resources=spectrasyncs/finalizers,verbs=update
// +kubebuilder:rbac:groups=batch,resources=jobs,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=batch,resources=cronjobs,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=configmaps,verbs=get;list;watch
// +kubebuilder:rbac:groups="",resources=secrets,verbs=get;list;watch
// +kubebuilder:rbac:groups="",resources=persistentvolumeclaims,verbs=get;list;watch
// +kubebuilder:rbac:groups="",resources=events,verbs=create;patch

// Reconcile handles SpectraSync resources
func (r *SpectraSyncReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	// Fetch the SpectraSync instance
	spectraSync := &spectrav1alpha1.SpectraSync{}
	if err := r.Get(ctx, req.NamespacedName, spectraSync); err != nil {
		if errors.IsNotFound(err) {
			logger.Info("SpectraSync resource not found, ignoring")
			return ctrl.Result{}, nil
		}
		logger.Error(err, "Failed to get SpectraSync")
		return ctrl.Result{}, err
	}

	// Handle deletion
	if !spectraSync.ObjectMeta.DeletionTimestamp.IsZero() {
		return r.handleDeletion(ctx, spectraSync)
	}

	// Add finalizer if not present
	if !controllerutil.ContainsFinalizer(spectraSync, spectraSyncFinalizer) {
		controllerutil.AddFinalizer(spectraSync, spectraSyncFinalizer)
		if err := r.Update(ctx, spectraSync); err != nil {
			return ctrl.Result{}, err
		}
	}

	// Check if suspended
	if spectraSync.Spec.Suspend {
		logger.Info("SpectraSync is suspended, skipping reconciliation")
		return ctrl.Result{}, nil
	}

	// Handle scheduled syncs
	if spectraSync.Spec.Schedule != "" {
		return r.reconcileScheduledSync(ctx, spectraSync)
	}

	// Handle one-time sync
	return r.reconcileOneTimeSync(ctx, spectraSync)
}

// handleDeletion handles the deletion of a SpectraSync
func (r *SpectraSyncReconciler) handleDeletion(ctx context.Context, spectraSync *spectrav1alpha1.SpectraSync) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	if controllerutil.ContainsFinalizer(spectraSync, spectraSyncFinalizer) {
		// Clean up associated resources
		if err := r.cleanupResources(ctx, spectraSync); err != nil {
			logger.Error(err, "Failed to cleanup resources")
			return ctrl.Result{}, err
		}

		// Remove finalizer
		controllerutil.RemoveFinalizer(spectraSync, spectraSyncFinalizer)
		if err := r.Update(ctx, spectraSync); err != nil {
			return ctrl.Result{}, err
		}
	}

	return ctrl.Result{}, nil
}

// cleanupResources cleans up resources associated with the SpectraSync
func (r *SpectraSyncReconciler) cleanupResources(ctx context.Context, spectraSync *spectrav1alpha1.SpectraSync) error {
	logger := log.FromContext(ctx)

	// Delete associated CronJob if exists
	cronJob := &batchv1.CronJob{}
	cronJobName := types.NamespacedName{
		Namespace: spectraSync.Namespace,
		Name:      fmt.Sprintf("%s-sync", spectraSync.Name),
	}
	if err := r.Get(ctx, cronJobName, cronJob); err == nil {
		if err := r.Delete(ctx, cronJob); err != nil {
			logger.Error(err, "Failed to delete CronJob")
			return err
		}
		logger.Info("Deleted CronJob", "name", cronJobName.Name)
	}

	return nil
}

// reconcileScheduledSync handles scheduled sync reconciliation
func (r *SpectraSyncReconciler) reconcileScheduledSync(ctx context.Context, spectraSync *spectrav1alpha1.SpectraSync) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	cronJobName := fmt.Sprintf("%s-sync", spectraSync.Name)

	// Check if CronJob exists
	existingCronJob := &batchv1.CronJob{}
	err := r.Get(ctx, types.NamespacedName{
		Namespace: spectraSync.Namespace,
		Name:      cronJobName,
	}, existingCronJob)

	cronJob := r.buildCronJob(spectraSync, cronJobName)

	if err != nil {
		if errors.IsNotFound(err) {
			// Create new CronJob
			if err := controllerutil.SetControllerReference(spectraSync, cronJob, r.Scheme); err != nil {
				return ctrl.Result{}, err
			}
			if err := r.Create(ctx, cronJob); err != nil {
				logger.Error(err, "Failed to create CronJob")
				r.Recorder.Event(spectraSync, corev1.EventTypeWarning, "CreateFailed", "Failed to create CronJob")
				return ctrl.Result{}, err
			}
			logger.Info("Created CronJob", "name", cronJobName)
			r.Recorder.Event(spectraSync, corev1.EventTypeNormal, "Created", "Created CronJob")
		} else {
			return ctrl.Result{}, err
		}
	} else {
		// Update existing CronJob if needed
		existingCronJob.Spec = cronJob.Spec
		if err := r.Update(ctx, existingCronJob); err != nil {
			logger.Error(err, "Failed to update CronJob")
			return ctrl.Result{}, err
		}
	}

	// Update status with next sync time
	if err := r.updateNextSyncTime(ctx, spectraSync); err != nil {
		logger.Error(err, "Failed to update next sync time")
	}

	return ctrl.Result{RequeueAfter: 5 * time.Minute}, nil
}

// reconcileOneTimeSync handles one-time sync reconciliation
func (r *SpectraSyncReconciler) reconcileOneTimeSync(ctx context.Context, spectraSync *spectrav1alpha1.SpectraSync) (ctrl.Result, error) {
	logger := log.FromContext(ctx)

	// Check if a sync job already completed
	if spectraSync.Status.LastSyncResult == spectrav1alpha1.SyncResultSuccess {
		logger.Info("One-time sync already completed")
		return ctrl.Result{}, nil
	}

	jobName := fmt.Sprintf("%s-sync-%d", spectraSync.Name, time.Now().Unix())

	// Create job
	job := r.buildJob(spectraSync, jobName)
	if err := controllerutil.SetControllerReference(spectraSync, job, r.Scheme); err != nil {
		return ctrl.Result{}, err
	}

	if err := r.Create(ctx, job); err != nil {
		logger.Error(err, "Failed to create sync job")
		r.Recorder.Event(spectraSync, corev1.EventTypeWarning, "CreateFailed", "Failed to create sync job")
		return ctrl.Result{}, err
	}

	logger.Info("Created sync job", "name", jobName)
	r.Recorder.Event(spectraSync, corev1.EventTypeNormal, "SyncStarted", "Started sync job")

	// Update status
	spectraSync.Status.LastSyncResult = spectrav1alpha1.SyncResultRunning
	spectraSync.Status.LastSyncTime = &metav1.Time{Time: time.Now()}
	if err := r.Status().Update(ctx, spectraSync); err != nil {
		logger.Error(err, "Failed to update status")
	}

	return ctrl.Result{RequeueAfter: 30 * time.Second}, nil
}

// buildCronJob creates a CronJob for scheduled syncs
func (r *SpectraSyncReconciler) buildCronJob(spectraSync *spectrav1alpha1.SpectraSync, name string) *batchv1.CronJob {
	job := r.buildJob(spectraSync, name)

	suspend := spectraSync.Spec.Suspend
	successfulJobsHistoryLimit := int32(3)
	failedJobsHistoryLimit := int32(3)

	if spectraSync.Spec.SuccessfulSyncsHistoryLimit != nil {
		successfulJobsHistoryLimit = *spectraSync.Spec.SuccessfulSyncsHistoryLimit
	}
	if spectraSync.Spec.FailedSyncsHistoryLimit != nil {
		failedJobsHistoryLimit = *spectraSync.Spec.FailedSyncsHistoryLimit
	}

	return &batchv1.CronJob{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: spectraSync.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":       "spectra-sync",
				"app.kubernetes.io/instance":   spectraSync.Name,
				"app.kubernetes.io/part-of":    "spectra",
				"app.kubernetes.io/managed-by": "spectra-operator",
			},
		},
		Spec: batchv1.CronJobSpec{
			Schedule:                   spectraSync.Spec.Schedule,
			Suspend:                    &suspend,
			ConcurrencyPolicy:          batchv1.ConcurrencyPolicy(spectraSync.Spec.ConcurrencyPolicy),
			SuccessfulJobsHistoryLimit: &successfulJobsHistoryLimit,
			FailedJobsHistoryLimit:     &failedJobsHistoryLimit,
			JobTemplate: batchv1.JobTemplateSpec{
				Spec: job.Spec,
			},
		},
	}
}

// buildJob creates a Job for running spectra sync
func (r *SpectraSyncReconciler) buildJob(spectraSync *spectrav1alpha1.SpectraSync, name string) *batchv1.Job {
	backoffLimit := int32(3)
	if spectraSync.Spec.BackoffLimit != nil {
		backoffLimit = *spectraSync.Spec.BackoffLimit
	}

	activeDeadlineSeconds := int64(3600)
	if spectraSync.Spec.ActiveDeadlineSeconds != nil {
		activeDeadlineSeconds = *spectraSync.Spec.ActiveDeadlineSeconds
	}

	// Build command arguments
	args := r.buildSpectraArgs(spectraSync)

	// Build environment variables
	envVars := r.buildEnvVars(spectraSync)

	// Build volumes and mounts
	volumes, volumeMounts := r.buildVolumes(spectraSync)

	return &batchv1.Job{
		ObjectMeta: metav1.ObjectMeta{
			Name:      name,
			Namespace: spectraSync.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name":       "spectra-sync",
				"app.kubernetes.io/instance":   spectraSync.Name,
				"app.kubernetes.io/part-of":    "spectra",
				"app.kubernetes.io/managed-by": "spectra-operator",
			},
		},
		Spec: batchv1.JobSpec{
			BackoffLimit:          &backoffLimit,
			ActiveDeadlineSeconds: &activeDeadlineSeconds,
			Template: corev1.PodTemplateSpec{
				ObjectMeta: metav1.ObjectMeta{
					Labels: map[string]string{
						"app.kubernetes.io/name":     "spectra-sync",
						"app.kubernetes.io/instance": spectraSync.Name,
					},
				},
				Spec: corev1.PodSpec{
					RestartPolicy: corev1.RestartPolicyOnFailure,
					Containers: []corev1.Container{
						{
							Name:         "spectra",
							Image:        r.SpectraImage,
							Args:         args,
							Env:          envVars,
							VolumeMounts: volumeMounts,
							Resources: corev1.ResourceRequirements{
								Requests: corev1.ResourceList{
									corev1.ResourceCPU:    "100m",
									corev1.ResourceMemory: "128Mi",
								},
								Limits: corev1.ResourceList{
									corev1.ResourceCPU:    "500m",
									corev1.ResourceMemory: "512Mi",
								},
							},
						},
					},
					Volumes: volumes,
				},
			},
		},
	}
}

// buildSpectraArgs builds command arguments for spectra
func (r *SpectraSyncReconciler) buildSpectraArgs(spectraSync *spectrav1alpha1.SpectraSync) []string {
	args := []string{"sync"}

	// Add tracker type
	args = append(args, "--tracker", string(spectraSync.Spec.Tracker.Type))

	// Add source file path
	switch spectraSync.Spec.Source.Type {
	case spectrav1alpha1.SourceTypeConfigMap:
		args = append(args, "--markdown", "/data/spec.md")
	case spectrav1alpha1.SourceTypeGit:
		args = append(args, "--markdown", fmt.Sprintf("/repo/%s", spectraSync.Spec.Source.Git.Path))
	case spectrav1alpha1.SourceTypePVC:
		args = append(args, "--markdown", fmt.Sprintf("/data/%s", spectraSync.Spec.Source.PVC.Path))
	}

	// Add tracker-specific arguments
	if spectraSync.Spec.Tracker.EpicKey != "" {
		args = append(args, "--epic-key", spectraSync.Spec.Tracker.EpicKey)
	}
	if spectraSync.Spec.Tracker.Project != "" {
		args = append(args, "--project", spectraSync.Spec.Tracker.Project)
	}

	// Add options
	if spectraSync.Spec.DryRun {
		args = append(args, "--dry-run")
	} else {
		args = append(args, "--execute")
	}

	if spectraSync.Spec.Incremental {
		args = append(args, "--incremental")
	}

	// Add phases
	for _, phase := range spectraSync.Spec.Phases {
		if phase != spectrav1alpha1.SyncPhaseAll {
			args = append(args, "--phase", string(phase))
		}
	}

	return args
}

// buildEnvVars builds environment variables for the sync job
func (r *SpectraSyncReconciler) buildEnvVars(spectraSync *spectrav1alpha1.SpectraSync) []corev1.EnvVar {
	envVars := []corev1.EnvVar{}

	tracker := spectraSync.Spec.Tracker
	secretName := tracker.CredentialsSecret.Name
	emailKey := tracker.CredentialsSecret.EmailKey
	tokenKey := tracker.CredentialsSecret.TokenKey

	if emailKey == "" {
		emailKey = "email"
	}
	if tokenKey == "" {
		tokenKey = "token"
	}

	switch tracker.Type {
	case spectrav1alpha1.TrackerTypeJira:
		envVars = append(envVars,
			corev1.EnvVar{Name: "JIRA_URL", Value: tracker.URL},
			corev1.EnvVar{
				Name: "JIRA_EMAIL",
				ValueFrom: &corev1.EnvVarSource{
					SecretKeyRef: &corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{Name: secretName},
						Key:                  emailKey,
					},
				},
			},
			corev1.EnvVar{
				Name: "JIRA_API_TOKEN",
				ValueFrom: &corev1.EnvVarSource{
					SecretKeyRef: &corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{Name: secretName},
						Key:                  tokenKey,
					},
				},
			},
		)
	case spectrav1alpha1.TrackerTypeGitHub:
		envVars = append(envVars,
			corev1.EnvVar{Name: "GITHUB_OWNER", Value: tracker.Owner},
			corev1.EnvVar{Name: "GITHUB_REPO", Value: tracker.Repo},
			corev1.EnvVar{
				Name: "GITHUB_TOKEN",
				ValueFrom: &corev1.EnvVarSource{
					SecretKeyRef: &corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{Name: secretName},
						Key:                  tokenKey,
					},
				},
			},
		)
	case spectrav1alpha1.TrackerTypeLinear:
		envVars = append(envVars,
			corev1.EnvVar{Name: "LINEAR_TEAM_ID", Value: tracker.TeamID},
			corev1.EnvVar{
				Name: "LINEAR_API_KEY",
				ValueFrom: &corev1.EnvVarSource{
					SecretKeyRef: &corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{Name: secretName},
						Key:                  tokenKey,
					},
				},
			},
		)
	// Add more tracker types as needed
	default:
		envVars = append(envVars,
			corev1.EnvVar{
				Name: "API_TOKEN",
				ValueFrom: &corev1.EnvVarSource{
					SecretKeyRef: &corev1.SecretKeySelector{
						LocalObjectReference: corev1.LocalObjectReference{Name: secretName},
						Key:                  tokenKey,
					},
				},
			},
		)
	}

	return envVars
}

// buildVolumes builds volumes and mounts for the sync job
func (r *SpectraSyncReconciler) buildVolumes(spectraSync *spectrav1alpha1.SpectraSync) ([]corev1.Volume, []corev1.VolumeMount) {
	volumes := []corev1.Volume{}
	mounts := []corev1.VolumeMount{}

	switch spectraSync.Spec.Source.Type {
	case spectrav1alpha1.SourceTypeConfigMap:
		volumes = append(volumes, corev1.Volume{
			Name: "spec-data",
			VolumeSource: corev1.VolumeSource{
				ConfigMap: &corev1.ConfigMapVolumeSource{
					LocalObjectReference: corev1.LocalObjectReference{
						Name: spectraSync.Spec.Source.ConfigMap.Name,
					},
					Items: []corev1.KeyToPath{
						{
							Key:  spectraSync.Spec.Source.ConfigMap.Key,
							Path: "spec.md",
						},
					},
				},
			},
		})
		mounts = append(mounts, corev1.VolumeMount{
			Name:      "spec-data",
			MountPath: "/data",
			ReadOnly:  true,
		})
	case spectrav1alpha1.SourceTypePVC:
		volumes = append(volumes, corev1.Volume{
			Name: "spec-data",
			VolumeSource: corev1.VolumeSource{
				PersistentVolumeClaim: &corev1.PersistentVolumeClaimVolumeSource{
					ClaimName: spectraSync.Spec.Source.PVC.ClaimName,
					ReadOnly:  true,
				},
			},
		})
		mounts = append(mounts, corev1.VolumeMount{
			Name:      "spec-data",
			MountPath: "/data",
			ReadOnly:  true,
		})
	case spectrav1alpha1.SourceTypeGit:
		// For git sources, use an init container to clone the repo
		volumes = append(volumes, corev1.Volume{
			Name: "repo",
			VolumeSource: corev1.VolumeSource{
				EmptyDir: &corev1.EmptyDirVolumeSource{},
			},
		})
		mounts = append(mounts, corev1.VolumeMount{
			Name:      "repo",
			MountPath: "/repo",
		})
	}

	return volumes, mounts
}

// updateNextSyncTime calculates and updates the next sync time
func (r *SpectraSyncReconciler) updateNextSyncTime(ctx context.Context, spectraSync *spectrav1alpha1.SpectraSync) error {
	if spectraSync.Spec.Schedule == "" {
		return nil
	}

	parser := cron.NewParser(cron.Minute | cron.Hour | cron.Dom | cron.Month | cron.Dow)
	schedule, err := parser.Parse(spectraSync.Spec.Schedule)
	if err != nil {
		return err
	}

	nextTime := schedule.Next(time.Now())
	spectraSync.Status.NextSyncTime = &metav1.Time{Time: nextTime}
	spectraSync.Status.ObservedGeneration = spectraSync.Generation

	return r.Status().Update(ctx, spectraSync)
}

// SetupWithManager sets up the controller with the Manager
func (r *SpectraSyncReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&spectrav1alpha1.SpectraSync{}).
		Owns(&batchv1.Job{}).
		Owns(&batchv1.CronJob{}).
		Complete(r)
}
