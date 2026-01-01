// Copyright (c) spectra
// SPDX-License-Identifier: MIT

import * as pulumi from "@pulumi/pulumi";
import * as k8s from "@pulumi/kubernetes";
import {
    BaseSyncArgs,
    SyncOutputs,
} from "../types";
import {
    trackerToEnvVars,
    buildSpectraArgs,
    normalizeCronSchedule,
    mergeTags,
} from "../utils";

/**
 * Kubernetes CronJob sync arguments
 */
export interface CronJobSyncArgs extends BaseSyncArgs {
    /**
     * Kubernetes namespace
     */
    namespace?: pulumi.Input<string>;

    /**
     * Spectra container image
     */
    image?: pulumi.Input<string>;

    /**
     * CPU request
     */
    cpuRequest?: pulumi.Input<string>;

    /**
     * Memory request
     */
    memoryRequest?: pulumi.Input<string>;

    /**
     * CPU limit
     */
    cpuLimit?: pulumi.Input<string>;

    /**
     * Memory limit
     */
    memoryLimit?: pulumi.Input<string>;

    /**
     * Number of successful jobs to keep
     */
    successfulJobsHistoryLimit?: pulumi.Input<number>;

    /**
     * Number of failed jobs to keep
     */
    failedJobsHistoryLimit?: pulumi.Input<number>;
}

/**
 * CronJobSync creates a Kubernetes CronJob for running Spectra syncs
 */
export class CronJobSync extends pulumi.ComponentResource implements SyncOutputs {
    public readonly name: pulumi.Output<string>;
    public readonly arn?: pulumi.Output<string>;
    public readonly logGroupName?: pulumi.Output<string>;
    public readonly secretArn?: pulumi.Output<string>;

    public readonly secret: k8s.core.v1.Secret;
    public readonly cronJob: k8s.batch.v1.CronJob;

    constructor(
        name: string,
        args: CronJobSyncArgs,
        opts?: pulumi.ComponentResourceOptions
    ) {
        super("spectra:kubernetes:CronJobSync", name, {}, opts);

        const defaultOpts = { parent: this };
        const namespace = args.namespace ?? "default";
        const labels = mergeTags(args.tags as Record<string, string>);
        const image = args.image ?? "spectra/spectra:latest";

        // Create secret for credentials
        const secretData: Record<string, pulumi.Input<string>> = {};
        const creds = args.tracker.credentials;

        if (creds.email) secretData["email"] = creds.email;
        if (creds.apiToken) secretData["api-token"] = creds.apiToken;
        if (creds.token) secretData["token"] = creds.token;
        if (creds.apiKey) secretData["api-key"] = creds.apiKey;

        this.secret = new k8s.core.v1.Secret(
            `${name}-credentials`,
            {
                metadata: {
                    name: `${name}-credentials`,
                    namespace: namespace,
                    labels: labels,
                },
                stringData: secretData,
            },
            defaultOpts
        );

        // Build environment variables
        const envVars = trackerToEnvVars(args.tracker);
        const envList = Object.entries(envVars).map(([name, value]) => {
            // Use secretKeyRef for sensitive values
            if (name.includes("TOKEN") || name.includes("KEY") || name.includes("PASSWORD")) {
                const secretKey = name.toLowerCase().replace(/_/g, "-");
                return {
                    name,
                    valueFrom: {
                        secretKeyRef: {
                            name: this.secret.metadata.name,
                            key: secretKey,
                        },
                    },
                };
            }
            return { name, value: value as string };
        });

        // Build command
        const command = buildSpectraArgs(args.tracker, {
            markdownPath: "/data/spec.md",
            dryRun: args.dryRun,
            phases: args.phases as string[],
            incremental: args.incremental,
        });

        // Determine schedule
        const schedule = args.schedule
            ? normalizeCronSchedule(args.schedule as string)
            : "0 */6 * * *";

        // Create CronJob
        this.cronJob = new k8s.batch.v1.CronJob(
            name,
            {
                metadata: {
                    name: name,
                    namespace: namespace,
                    labels: labels,
                },
                spec: {
                    schedule: schedule,
                    concurrencyPolicy: "Forbid",
                    successfulJobsHistoryLimit: args.successfulJobsHistoryLimit ?? 3,
                    failedJobsHistoryLimit: args.failedJobsHistoryLimit ?? 3,
                    jobTemplate: {
                        spec: {
                            backoffLimit: 3,
                            template: {
                                metadata: {
                                    labels: labels,
                                },
                                spec: {
                                    restartPolicy: "OnFailure",
                                    containers: [
                                        {
                                            name: "spectra",
                                            image: image,
                                            command: command,
                                            env: envList,
                                            resources: {
                                                requests: {
                                                    cpu: args.cpuRequest ?? "100m",
                                                    memory: args.memoryRequest ?? "128Mi",
                                                },
                                                limits: {
                                                    cpu: args.cpuLimit ?? "500m",
                                                    memory: args.memoryLimit ?? "512Mi",
                                                },
                                            },
                                        },
                                    ],
                                },
                            },
                        },
                    },
                },
            },
            defaultOpts
        );

        this.name = this.cronJob.metadata.name;

        this.registerOutputs({
            name: this.name,
        });
    }
}
