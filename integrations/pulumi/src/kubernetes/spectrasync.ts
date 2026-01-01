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
    normalizeCronSchedule,
    mergeTags,
} from "../utils";

/**
 * Kubernetes SpectraSync CRD arguments
 */
export interface SpectraSyncArgs extends BaseSyncArgs {
    /**
     * Kubernetes namespace
     */
    namespace?: pulumi.Input<string>;

    /**
     * Spectra container image
     */
    image?: pulumi.Input<string>;
}

/**
 * SpectraSync creates a Spectra custom resource for Kubernetes
 */
export class SpectraSync extends pulumi.ComponentResource implements SyncOutputs {
    public readonly name: pulumi.Output<string>;
    public readonly arn?: pulumi.Output<string>;
    public readonly logGroupName?: pulumi.Output<string>;
    public readonly secretArn?: pulumi.Output<string>;

    public readonly secret: k8s.core.v1.Secret;
    public readonly customResource: k8s.apiextensions.CustomResource;

    constructor(
        name: string,
        args: SpectraSyncArgs,
        opts?: pulumi.ComponentResourceOptions
    ) {
        super("spectra:kubernetes:SpectraSync", name, {}, opts);

        const defaultOpts = { parent: this };
        const namespace = args.namespace ?? "default";
        const labels = mergeTags(args.tags as Record<string, string>);

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

        // Build tracker spec
        const trackerSpec: Record<string, unknown> = {
            type: args.tracker.type,
            credentialsSecret: {
                name: this.secret.metadata.name,
            },
        };

        if (args.tracker.type === "jira") {
            trackerSpec.url = (args.tracker as any).url;
            trackerSpec.project = (args.tracker as any).project;
            trackerSpec.epicKey = (args.tracker as any).epicKey;
        } else if (args.tracker.type === "github") {
            trackerSpec.owner = (args.tracker as any).owner;
            trackerSpec.repo = (args.tracker as any).repo;
        } else if (args.tracker.type === "linear") {
            trackerSpec.teamId = (args.tracker as any).teamId;
        }

        // Build source spec
        const sourceSpec: Record<string, unknown> = {
            type: (args.source as any).type,
        };

        if ((args.source as any).type === "configmap") {
            sourceSpec.configMap = {
                name: (args.source as any).configMapName,
                key: (args.source as any).key,
            };
        } else if ((args.source as any).type === "pvc") {
            sourceSpec.pvc = {
                claimName: (args.source as any).claimName,
                path: (args.source as any).path,
            };
        } else if ((args.source as any).type === "git") {
            sourceSpec.git = {
                repository: (args.source as any).repository,
                branch: (args.source as any).branch ?? "main",
                path: (args.source as any).path,
            };
        }

        // Create SpectraSync custom resource
        this.customResource = new k8s.apiextensions.CustomResource(
            name,
            {
                apiVersion: "spectra.io/v1alpha1",
                kind: "SpectraSync",
                metadata: {
                    name: name,
                    namespace: namespace,
                    labels: labels,
                },
                spec: {
                    source: sourceSpec,
                    tracker: trackerSpec,
                    schedule: args.schedule
                        ? normalizeCronSchedule(args.schedule as string)
                        : undefined,
                    dryRun: args.dryRun ?? false,
                    phases: args.phases ?? ["all"],
                    incremental: args.incremental ?? false,
                    bidirectional: args.bidirectional ?? false,
                },
            },
            defaultOpts
        );

        this.name = this.customResource.metadata.name;

        this.registerOutputs({
            name: this.name,
        });
    }
}
