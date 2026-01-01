// Copyright (c) spectra
// SPDX-License-Identifier: MIT

import * as pulumi from "@pulumi/pulumi";
import {
    BaseSyncArgs,
    SyncOutputs,
} from "../types";
import { mergeTags } from "../utils";

/**
 * GCP Cloud Run sync arguments
 */
export interface CloudRunSyncArgs extends BaseSyncArgs {
    /**
     * Spectra container image
     */
    image?: pulumi.Input<string>;

    /**
     * GCP project ID
     */
    project?: pulumi.Input<string>;

    /**
     * GCP region
     */
    region?: pulumi.Input<string>;

    /**
     * CPU limit
     */
    cpu?: pulumi.Input<string>;

    /**
     * Memory limit
     */
    memory?: pulumi.Input<string>;
}

/**
 * CloudRunSync creates a GCP Cloud Run job for running Spectra syncs
 *
 * Note: This is a placeholder implementation. Full implementation requires
 * @pulumi/gcp package to be available.
 */
export class CloudRunSync extends pulumi.ComponentResource implements SyncOutputs {
    public readonly name: pulumi.Output<string>;
    public readonly arn?: pulumi.Output<string>;
    public readonly logGroupName?: pulumi.Output<string>;
    public readonly secretArn?: pulumi.Output<string>;

    constructor(
        name: string,
        args: CloudRunSyncArgs,
        opts?: pulumi.ComponentResourceOptions
    ) {
        super("spectra:gcp:CloudRunSync", name, {}, opts);

        const labels = mergeTags(args.tags as Record<string, string>);

        // Note: Full implementation would use @pulumi/gcp
        // This is a placeholder showing the structure

        this.name = pulumi.output(name);

        this.registerOutputs({
            name: this.name,
        });
    }
}
