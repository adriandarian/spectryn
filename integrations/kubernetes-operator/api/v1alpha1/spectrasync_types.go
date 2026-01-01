// Copyright (c) spectra
// SPDX-License-Identifier: MIT

package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// TrackerType defines the type of issue tracker
// +kubebuilder:validation:Enum=jira;github;azure-devops;linear;gitlab;trello;asana;monday;shortcut;clickup;youtrack;plane;pivotal;basecamp;bitbucket
type TrackerType string

const (
	TrackerTypeJira        TrackerType = "jira"
	TrackerTypeGitHub      TrackerType = "github"
	TrackerTypeAzureDevOps TrackerType = "azure-devops"
	TrackerTypeLinear      TrackerType = "linear"
	TrackerTypeGitLab      TrackerType = "gitlab"
	TrackerTypeTrello      TrackerType = "trello"
	TrackerTypeAsana       TrackerType = "asana"
	TrackerTypeMonday      TrackerType = "monday"
	TrackerTypeShortcut    TrackerType = "shortcut"
	TrackerTypeClickUp     TrackerType = "clickup"
	TrackerTypeYouTrack    TrackerType = "youtrack"
	TrackerTypePlane       TrackerType = "plane"
	TrackerTypePivotal     TrackerType = "pivotal"
	TrackerTypeBasecamp    TrackerType = "basecamp"
	TrackerTypeBitbucket   TrackerType = "bitbucket"
)

// SourceType defines the type of markdown source
// +kubebuilder:validation:Enum=configmap;git;pvc
type SourceType string

const (
	SourceTypeConfigMap SourceType = "configmap"
	SourceTypeGit       SourceType = "git"
	SourceTypePVC       SourceType = "pvc"
)

// SyncPhase defines a sync phase
// +kubebuilder:validation:Enum=all;descriptions;subtasks;comments;statuses;attachments
type SyncPhase string

const (
	SyncPhaseAll         SyncPhase = "all"
	SyncPhaseDescriptions SyncPhase = "descriptions"
	SyncPhaseSubtasks    SyncPhase = "subtasks"
	SyncPhaseComments    SyncPhase = "comments"
	SyncPhaseStatuses    SyncPhase = "statuses"
	SyncPhaseAttachments SyncPhase = "attachments"
)

// ConcurrencyPolicy describes how the sync will be handled
// +kubebuilder:validation:Enum=Allow;Forbid;Replace
type ConcurrencyPolicy string

const (
	AllowConcurrent   ConcurrencyPolicy = "Allow"
	ForbidConcurrent  ConcurrencyPolicy = "Forbid"
	ReplaceConcurrent ConcurrencyPolicy = "Replace"
)

// SyncResult represents the result of a sync operation
type SyncResult string

const (
	SyncResultSuccess SyncResult = "Success"
	SyncResultFailed  SyncResult = "Failed"
	SyncResultRunning SyncResult = "Running"
	SyncResultPending SyncResult = "Pending"
)

// SpectraSyncSpec defines the desired state of SpectraSync
type SpectraSyncSpec struct {
	// Source defines where to get markdown files
	// +kubebuilder:validation:Required
	Source SourceSpec `json:"source"`

	// Tracker defines the target issue tracker
	// +kubebuilder:validation:Required
	Tracker TrackerSpec `json:"tracker"`

	// Schedule in cron format for automated syncs
	// +optional
	Schedule string `json:"schedule,omitempty"`

	// DryRun runs sync without making changes
	// +kubebuilder:default=false
	// +optional
	DryRun bool `json:"dryRun,omitempty"`

	// Phases to sync
	// +kubebuilder:default={"all"}
	// +optional
	Phases []SyncPhase `json:"phases,omitempty"`

	// Incremental only syncs changed items
	// +kubebuilder:default=false
	// +optional
	Incremental bool `json:"incremental,omitempty"`

	// Bidirectional enables two-way sync
	// +kubebuilder:default=false
	// +optional
	Bidirectional bool `json:"bidirectional,omitempty"`

	// Suspend prevents scheduled syncs
	// +kubebuilder:default=false
	// +optional
	Suspend bool `json:"suspend,omitempty"`

	// ConcurrencyPolicy for handling concurrent syncs
	// +kubebuilder:default=Forbid
	// +optional
	ConcurrencyPolicy ConcurrencyPolicy `json:"concurrencyPolicy,omitempty"`

	// SuccessfulSyncsHistoryLimit is the number of successful syncs to retain
	// +kubebuilder:default=3
	// +kubebuilder:validation:Minimum=0
	// +optional
	SuccessfulSyncsHistoryLimit *int32 `json:"successfulSyncsHistoryLimit,omitempty"`

	// FailedSyncsHistoryLimit is the number of failed syncs to retain
	// +kubebuilder:default=3
	// +kubebuilder:validation:Minimum=0
	// +optional
	FailedSyncsHistoryLimit *int32 `json:"failedSyncsHistoryLimit,omitempty"`

	// BackoffLimit is the number of retries before marking sync as failed
	// +kubebuilder:default=3
	// +kubebuilder:validation:Minimum=0
	// +optional
	BackoffLimit *int32 `json:"backoffLimit,omitempty"`

	// ActiveDeadlineSeconds is the maximum time for a sync job
	// +kubebuilder:default=3600
	// +kubebuilder:validation:Minimum=0
	// +optional
	ActiveDeadlineSeconds *int64 `json:"activeDeadlineSeconds,omitempty"`

	// Notifications configures sync notifications
	// +optional
	Notifications *NotificationSpec `json:"notifications,omitempty"`
}

// SourceSpec defines the markdown source
type SourceSpec struct {
	// Type of source
	// +kubebuilder:validation:Required
	Type SourceType `json:"type"`

	// ConfigMap source
	// +optional
	ConfigMap *ConfigMapSourceSpec `json:"configMap,omitempty"`

	// Git source
	// +optional
	Git *GitSourceSpec `json:"git,omitempty"`

	// PVC source
	// +optional
	PVC *PVCSourceSpec `json:"pvc,omitempty"`
}

// ConfigMapSourceSpec defines a ConfigMap source
type ConfigMapSourceSpec struct {
	// Name of the ConfigMap
	// +kubebuilder:validation:Required
	Name string `json:"name"`

	// Key containing the markdown content
	// +kubebuilder:validation:Required
	Key string `json:"key"`
}

// GitSourceSpec defines a Git repository source
type GitSourceSpec struct {
	// Repository URL
	// +kubebuilder:validation:Required
	Repository string `json:"repository"`

	// Branch to clone
	// +kubebuilder:default=main
	// +optional
	Branch string `json:"branch,omitempty"`

	// Path to markdown file in repository
	// +kubebuilder:validation:Required
	Path string `json:"path"`

	// CredentialsSecret for git authentication
	// +optional
	CredentialsSecret *SecretKeySelector `json:"credentialsSecret,omitempty"`
}

// PVCSourceSpec defines a PersistentVolumeClaim source
type PVCSourceSpec struct {
	// ClaimName is the name of the PVC
	// +kubebuilder:validation:Required
	ClaimName string `json:"claimName"`

	// Path to markdown file in the volume
	// +kubebuilder:validation:Required
	Path string `json:"path"`
}

// TrackerSpec defines the target issue tracker
type TrackerSpec struct {
	// Type of tracker
	// +kubebuilder:validation:Required
	Type TrackerType `json:"type"`

	// URL for the tracker (Jira, GitLab, YouTrack, etc.)
	// +optional
	URL string `json:"url,omitempty"`

	// Project key or ID
	// +optional
	Project string `json:"project,omitempty"`

	// EpicKey for Jira
	// +optional
	EpicKey string `json:"epicKey,omitempty"`

	// Owner for GitHub/GitLab
	// +optional
	Owner string `json:"owner,omitempty"`

	// Repo for GitHub/GitLab/Bitbucket
	// +optional
	Repo string `json:"repo,omitempty"`

	// Organization for Azure DevOps
	// +optional
	Organization string `json:"organization,omitempty"`

	// TeamID for Linear
	// +optional
	TeamID string `json:"teamId,omitempty"`

	// Workspace for various trackers
	// +optional
	Workspace string `json:"workspace,omitempty"`

	// APIUrl for self-hosted instances
	// +optional
	APIUrl string `json:"apiUrl,omitempty"`

	// CredentialsSecret for tracker authentication
	// +kubebuilder:validation:Required
	CredentialsSecret CredentialsSecretSpec `json:"credentialsSecret"`
}

// CredentialsSecretSpec defines the secret containing credentials
type CredentialsSecretSpec struct {
	// Name of the Secret
	// +kubebuilder:validation:Required
	Name string `json:"name"`

	// EmailKey is the key for the email/username
	// +kubebuilder:default=email
	// +optional
	EmailKey string `json:"emailKey,omitempty"`

	// TokenKey is the key for the API token
	// +kubebuilder:default=token
	// +optional
	TokenKey string `json:"tokenKey,omitempty"`

	// PasswordKey is the key for the password
	// +kubebuilder:default=password
	// +optional
	PasswordKey string `json:"passwordKey,omitempty"`
}

// SecretKeySelector defines a secret key reference
type SecretKeySelector struct {
	// Name of the Secret
	// +kubebuilder:validation:Required
	Name string `json:"name"`

	// UsernameKey is the key for username
	// +kubebuilder:default=username
	// +optional
	UsernameKey string `json:"usernameKey,omitempty"`

	// PasswordKey is the key for password/token
	// +kubebuilder:default=password
	// +optional
	PasswordKey string `json:"passwordKey,omitempty"`
}

// NotificationSpec defines notification settings
type NotificationSpec struct {
	// Slack notification settings
	// +optional
	Slack *SlackNotificationSpec `json:"slack,omitempty"`

	// Email notification settings
	// +optional
	Email *EmailNotificationSpec `json:"email,omitempty"`
}

// SlackNotificationSpec defines Slack notification settings
type SlackNotificationSpec struct {
	// WebhookURL for Slack
	// +kubebuilder:validation:Required
	WebhookURL string `json:"webhookUrl"`

	// Channel to post to
	// +optional
	Channel string `json:"channel,omitempty"`

	// OnSuccess sends notification on success
	// +kubebuilder:default=false
	// +optional
	OnSuccess bool `json:"onSuccess,omitempty"`

	// OnFailure sends notification on failure
	// +kubebuilder:default=true
	// +optional
	OnFailure bool `json:"onFailure,omitempty"`
}

// EmailNotificationSpec defines email notification settings
type EmailNotificationSpec struct {
	// Recipients email addresses
	// +kubebuilder:validation:MinItems=1
	Recipients []string `json:"recipients"`

	// OnSuccess sends notification on success
	// +kubebuilder:default=false
	// +optional
	OnSuccess bool `json:"onSuccess,omitempty"`

	// OnFailure sends notification on failure
	// +kubebuilder:default=true
	// +optional
	OnFailure bool `json:"onFailure,omitempty"`
}

// SpectraSyncStatus defines the observed state of SpectraSync
type SpectraSyncStatus struct {
	// LastSyncTime is the time of the last sync attempt
	// +optional
	LastSyncTime *metav1.Time `json:"lastSyncTime,omitempty"`

	// LastSuccessfulSyncTime is the time of the last successful sync
	// +optional
	LastSuccessfulSyncTime *metav1.Time `json:"lastSuccessfulSyncTime,omitempty"`

	// LastSyncResult is the result of the last sync
	// +optional
	LastSyncResult SyncResult `json:"lastSyncResult,omitempty"`

	// NextSyncTime is the next scheduled sync time
	// +optional
	NextSyncTime *metav1.Time `json:"nextSyncTime,omitempty"`

	// ObservedGeneration is the last observed generation
	// +optional
	ObservedGeneration int64 `json:"observedGeneration,omitempty"`

	// SyncCount is the total number of sync attempts
	// +optional
	SyncCount int32 `json:"syncCount,omitempty"`

	// SuccessCount is the number of successful syncs
	// +optional
	SuccessCount int32 `json:"successCount,omitempty"`

	// FailureCount is the number of failed syncs
	// +optional
	FailureCount int32 `json:"failureCount,omitempty"`

	// LastSyncStats contains statistics from the last sync
	// +optional
	LastSyncStats *SyncStats `json:"lastSyncStats,omitempty"`

	// Conditions represent the latest available observations
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// SyncHistory contains recent sync records
	// +optional
	SyncHistory []SyncRecord `json:"syncHistory,omitempty"`
}

// SyncStats contains sync statistics
type SyncStats struct {
	// StoriesCreated is the number of stories created
	StoriesCreated int32 `json:"storiesCreated,omitempty"`

	// StoriesUpdated is the number of stories updated
	StoriesUpdated int32 `json:"storiesUpdated,omitempty"`

	// SubtasksCreated is the number of subtasks created
	SubtasksCreated int32 `json:"subtasksCreated,omitempty"`

	// SubtasksUpdated is the number of subtasks updated
	SubtasksUpdated int32 `json:"subtasksUpdated,omitempty"`

	// Duration is the sync duration
	Duration string `json:"duration,omitempty"`
}

// SyncRecord represents a single sync execution
type SyncRecord struct {
	// SyncTime is when the sync occurred
	SyncTime metav1.Time `json:"syncTime"`

	// Result of the sync
	Result SyncResult `json:"result"`

	// Duration of the sync
	// +optional
	Duration string `json:"duration,omitempty"`

	// Message contains additional information
	// +optional
	Message string `json:"message,omitempty"`

	// Stats from the sync
	// +optional
	Stats *SyncStats `json:"stats,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:printcolumn:name="Tracker",type=string,JSONPath=`.spec.tracker.type`
// +kubebuilder:printcolumn:name="Schedule",type=string,JSONPath=`.spec.schedule`
// +kubebuilder:printcolumn:name="Last Sync",type=date,JSONPath=`.status.lastSyncTime`
// +kubebuilder:printcolumn:name="Status",type=string,JSONPath=`.status.lastSyncResult`
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// SpectraSync is the Schema for the spectrasyncs API
type SpectraSync struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   SpectraSyncSpec   `json:"spec,omitempty"`
	Status SpectraSyncStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// SpectraSyncList contains a list of SpectraSync
type SpectraSyncList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []SpectraSync `json:"items"`
}

func init() {
	SchemeBuilder.Register(&SpectraSync{}, &SpectraSyncList{})
}
