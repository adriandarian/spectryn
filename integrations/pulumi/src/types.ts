// Copyright (c) spectra
// SPDX-License-Identifier: MIT

import * as pulumi from "@pulumi/pulumi";

/**
 * Supported tracker types
 */
export type TrackerType =
    | "jira"
    | "github"
    | "azure-devops"
    | "linear"
    | "gitlab"
    | "trello"
    | "asana"
    | "monday"
    | "shortcut"
    | "clickup"
    | "youtrack"
    | "plane"
    | "pivotal"
    | "basecamp"
    | "bitbucket";

/**
 * Supported source types
 */
export type SourceType =
    | "s3"
    | "blob"
    | "gcs"
    | "git"
    | "configmap"
    | "pvc"
    | "inline";

/**
 * Sync phases
 */
export type SyncPhase =
    | "all"
    | "descriptions"
    | "subtasks"
    | "comments"
    | "statuses"
    | "attachments";

/**
 * Credentials configuration
 */
export interface CredentialsArgs {
    /**
     * Email address (for Jira, etc.)
     */
    email?: pulumi.Input<string>;

    /**
     * API token
     */
    apiToken?: pulumi.Input<string>;

    /**
     * Generic token (for GitHub, Linear, etc.)
     */
    token?: pulumi.Input<string>;

    /**
     * API key
     */
    apiKey?: pulumi.Input<string>;

    /**
     * Username for basic auth
     */
    username?: pulumi.Input<string>;

    /**
     * Password for basic auth
     */
    password?: pulumi.Input<string>;
}

/**
 * Jira-specific tracker configuration
 */
export interface JiraTrackerArgs {
    type: "jira";
    url: pulumi.Input<string>;
    project?: pulumi.Input<string>;
    epicKey: pulumi.Input<string>;
    credentials: CredentialsArgs;
}

/**
 * GitHub-specific tracker configuration
 */
export interface GitHubTrackerArgs {
    type: "github";
    owner: pulumi.Input<string>;
    repo: pulumi.Input<string>;
    credentials: CredentialsArgs;
}

/**
 * Azure DevOps-specific tracker configuration
 */
export interface AzureDevOpsTrackerArgs {
    type: "azure-devops";
    organization: pulumi.Input<string>;
    project: pulumi.Input<string>;
    credentials: CredentialsArgs;
}

/**
 * Linear-specific tracker configuration
 */
export interface LinearTrackerArgs {
    type: "linear";
    teamId: pulumi.Input<string>;
    credentials: CredentialsArgs;
}

/**
 * GitLab-specific tracker configuration
 */
export interface GitLabTrackerArgs {
    type: "gitlab";
    url?: pulumi.Input<string>;
    projectId: pulumi.Input<string>;
    credentials: CredentialsArgs;
}

/**
 * Generic tracker configuration for other trackers
 */
export interface GenericTrackerArgs {
    type: Exclude<TrackerType, "jira" | "github" | "azure-devops" | "linear" | "gitlab">;
    url?: pulumi.Input<string>;
    workspace?: pulumi.Input<string>;
    project?: pulumi.Input<string>;
    credentials: CredentialsArgs;
}

/**
 * Union type for all tracker configurations
 */
export type TrackerConfigArgs =
    | JiraTrackerArgs
    | GitHubTrackerArgs
    | AzureDevOpsTrackerArgs
    | LinearTrackerArgs
    | GitLabTrackerArgs
    | GenericTrackerArgs;

/**
 * S3 source configuration
 */
export interface S3SourceArgs {
    type: "s3";
    bucket: pulumi.Input<string>;
    key: pulumi.Input<string>;
    region?: pulumi.Input<string>;
}

/**
 * Azure Blob source configuration
 */
export interface BlobSourceArgs {
    type: "blob";
    storageAccount: pulumi.Input<string>;
    container: pulumi.Input<string>;
    blob: pulumi.Input<string>;
}

/**
 * GCS source configuration
 */
export interface GcsSourceArgs {
    type: "gcs";
    bucket: pulumi.Input<string>;
    object: pulumi.Input<string>;
}

/**
 * Git source configuration
 */
export interface GitSourceArgs {
    type: "git";
    repository: pulumi.Input<string>;
    branch?: pulumi.Input<string>;
    path: pulumi.Input<string>;
    credentials?: CredentialsArgs;
}

/**
 * ConfigMap source configuration (Kubernetes)
 */
export interface ConfigMapSourceArgs {
    type: "configmap";
    configMapName: pulumi.Input<string>;
    key: pulumi.Input<string>;
    namespace?: pulumi.Input<string>;
}

/**
 * PVC source configuration (Kubernetes)
 */
export interface PvcSourceArgs {
    type: "pvc";
    claimName: pulumi.Input<string>;
    path: pulumi.Input<string>;
}

/**
 * Inline source configuration
 */
export interface InlineSourceArgs {
    type: "inline";
    content: pulumi.Input<string>;
}

/**
 * Union type for all source configurations
 */
export type SourceConfigArgs =
    | S3SourceArgs
    | BlobSourceArgs
    | GcsSourceArgs
    | GitSourceArgs
    | ConfigMapSourceArgs
    | PvcSourceArgs
    | InlineSourceArgs;

/**
 * Monitoring configuration
 */
export interface MonitoringArgs {
    /**
     * Enable monitoring
     */
    enabled?: pulumi.Input<boolean>;

    /**
     * Create alarm on failure
     */
    alarmOnFailure?: pulumi.Input<boolean>;

    /**
     * Create CloudWatch/Azure Monitor dashboard
     */
    dashboardEnabled?: pulumi.Input<boolean>;

    /**
     * Log retention in days
     */
    logRetentionDays?: pulumi.Input<number>;
}

/**
 * Notification configuration
 */
export interface NotificationArgs {
    /**
     * Slack webhook URL
     */
    slackWebhookUrl?: pulumi.Input<string>;

    /**
     * Slack channel
     */
    slackChannel?: pulumi.Input<string>;

    /**
     * Email addresses for notifications
     */
    emailAddresses?: pulumi.Input<string>[];

    /**
     * Notify on success
     */
    onSuccess?: pulumi.Input<boolean>;

    /**
     * Notify on failure
     */
    onFailure?: pulumi.Input<boolean>;
}

/**
 * Base sync configuration
 */
export interface BaseSyncArgs {
    /**
     * Tracker configuration
     */
    tracker: TrackerConfigArgs;

    /**
     * Source configuration
     */
    source: SourceConfigArgs;

    /**
     * Schedule expression (cron or rate)
     */
    schedule?: pulumi.Input<string>;

    /**
     * Enable dry-run mode
     */
    dryRun?: pulumi.Input<boolean>;

    /**
     * Sync phases to execute
     */
    phases?: pulumi.Input<SyncPhase>[];

    /**
     * Enable incremental sync
     */
    incremental?: pulumi.Input<boolean>;

    /**
     * Enable bidirectional sync
     */
    bidirectional?: pulumi.Input<boolean>;

    /**
     * Monitoring configuration
     */
    monitoring?: MonitoringArgs;

    /**
     * Notification configuration
     */
    notifications?: NotificationArgs;

    /**
     * Resource tags
     */
    tags?: pulumi.Input<Record<string, string>>;
}

/**
 * Output types for sync resources
 */
export interface SyncOutputs {
    /**
     * Resource ARN/ID
     */
    arn?: pulumi.Output<string>;

    /**
     * Resource name
     */
    name: pulumi.Output<string>;

    /**
     * Log group/stream name
     */
    logGroupName?: pulumi.Output<string>;

    /**
     * Secret ARN/ID
     */
    secretArn?: pulumi.Output<string>;

    /**
     * Dashboard URL
     */
    dashboardUrl?: pulumi.Output<string>;
}
