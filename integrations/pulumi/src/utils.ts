// Copyright (c) spectra
// SPDX-License-Identifier: MIT

import * as pulumi from "@pulumi/pulumi";
import { TrackerConfigArgs, CredentialsArgs } from "./types";

/**
 * Convert tracker config to environment variables
 */
export function trackerToEnvVars(
    tracker: TrackerConfigArgs
): Record<string, pulumi.Input<string>> {
    const envVars: Record<string, pulumi.Input<string>> = {};

    switch (tracker.type) {
        case "jira":
            envVars["JIRA_URL"] = tracker.url;
            if (tracker.project) envVars["JIRA_PROJECT"] = tracker.project;
            envVars["EPIC_KEY"] = tracker.epicKey;
            if (tracker.credentials.email) {
                envVars["JIRA_EMAIL"] = tracker.credentials.email;
            }
            if (tracker.credentials.apiToken) {
                envVars["JIRA_API_TOKEN"] = tracker.credentials.apiToken;
            }
            break;

        case "github":
            envVars["GITHUB_OWNER"] = tracker.owner;
            envVars["GITHUB_REPO"] = tracker.repo;
            if (tracker.credentials.token) {
                envVars["GITHUB_TOKEN"] = tracker.credentials.token;
            }
            break;

        case "azure-devops":
            envVars["AZURE_ORGANIZATION"] = tracker.organization;
            envVars["AZURE_PROJECT"] = tracker.project;
            if (tracker.credentials.token) {
                envVars["AZURE_PAT"] = tracker.credentials.token;
            }
            break;

        case "linear":
            envVars["LINEAR_TEAM_ID"] = tracker.teamId;
            if (tracker.credentials.apiKey) {
                envVars["LINEAR_API_KEY"] = tracker.credentials.apiKey;
            }
            break;

        case "gitlab":
            if (tracker.url) envVars["GITLAB_URL"] = tracker.url;
            envVars["GITLAB_PROJECT_ID"] = tracker.projectId;
            if (tracker.credentials.token) {
                envVars["GITLAB_TOKEN"] = tracker.credentials.token;
            }
            break;

        default:
            envVars["TRACKER_TYPE"] = tracker.type;
            if (tracker.url) envVars["TRACKER_URL"] = tracker.url;
            if (tracker.workspace) envVars["TRACKER_WORKSPACE"] = tracker.workspace;
            if (tracker.project) envVars["TRACKER_PROJECT"] = tracker.project;
            if (tracker.credentials.token) {
                envVars["API_TOKEN"] = tracker.credentials.token;
            }
            if (tracker.credentials.apiKey) {
                envVars["API_KEY"] = tracker.credentials.apiKey;
            }
    }

    return envVars;
}

/**
 * Build spectra CLI command arguments
 */
export function buildSpectraArgs(
    tracker: TrackerConfigArgs,
    options: {
        markdownPath: string;
        dryRun?: boolean;
        phases?: string[];
        incremental?: boolean;
    }
): string[] {
    const args = ["spectra", "sync", "--tracker", tracker.type];

    args.push("--markdown", options.markdownPath);

    if (tracker.type === "jira") {
        args.push("--epic-key", tracker.epicKey as string);
    }

    if (options.dryRun) {
        args.push("--dry-run");
    } else {
        args.push("--execute");
    }

    if (options.incremental) {
        args.push("--incremental");
    }

    if (options.phases && options.phases.length > 0) {
        for (const phase of options.phases) {
            if (phase !== "all") {
                args.push("--phase", phase);
            }
        }
    }

    return args;
}

/**
 * Convert schedule to cron expression
 */
export function normalizeCronSchedule(schedule: string): string {
    // Handle AWS rate expressions
    if (schedule.startsWith("rate(")) {
        const match = schedule.match(/rate\((\d+)\s+(minute|hour|day)s?\)/);
        if (match) {
            const [, value, unit] = match;
            const num = parseInt(value, 10);

            switch (unit) {
                case "minute":
                    return `*/${num} * * * *`;
                case "hour":
                    return `0 */${num} * * *`;
                case "day":
                    return `0 0 */${num} * *`;
            }
        }
    }

    // Handle @hourly, @daily, etc.
    const shortcuts: Record<string, string> = {
        "@yearly": "0 0 1 1 *",
        "@annually": "0 0 1 1 *",
        "@monthly": "0 0 1 * *",
        "@weekly": "0 0 * * 0",
        "@daily": "0 0 * * *",
        "@hourly": "0 * * * *",
    };

    if (shortcuts[schedule]) {
        return shortcuts[schedule];
    }

    // Assume it's already a cron expression
    return schedule;
}

/**
 * Generate unique resource name
 */
export function generateResourceName(
    baseName: string,
    suffix?: string
): string {
    const sanitized = baseName.replace(/[^a-zA-Z0-9-]/g, "-").toLowerCase();
    const timestamp = Date.now().toString(36);

    if (suffix) {
        return `${sanitized}-${suffix}-${timestamp}`.substring(0, 63);
    }

    return `${sanitized}-${timestamp}`.substring(0, 63);
}

/**
 * Merge tags with defaults
 */
export function mergeTags(
    userTags?: Record<string, string>,
    defaults: Record<string, string> = {}
): Record<string, string> {
    return {
        ...defaults,
        ...userTags,
        "managed-by": "pulumi-spectra",
        application: "spectra",
    };
}

/**
 * Create secret JSON for credentials
 */
export function credentialsToSecretJson(
    credentials: CredentialsArgs,
    trackerType: string
): pulumi.Output<string> {
    const secretData: Record<string, pulumi.Input<string>> = {};

    if (credentials.email) secretData["email"] = credentials.email;
    if (credentials.apiToken) secretData["apiToken"] = credentials.apiToken;
    if (credentials.token) secretData["token"] = credentials.token;
    if (credentials.apiKey) secretData["apiKey"] = credentials.apiKey;
    if (credentials.username) secretData["username"] = credentials.username;
    if (credentials.password) secretData["password"] = credentials.password;

    return pulumi.output(secretData).apply((data) => JSON.stringify(data));
}
