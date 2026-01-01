// Copyright (c) spectra
// SPDX-License-Identifier: MIT

import * as pulumi from "@pulumi/pulumi";
import {
    BaseSyncArgs,
    SyncOutputs,
} from "../types";
import { mergeTags } from "../utils";

/**
 * Azure Container Instance sync arguments
 */
export interface ContainerInstanceSyncArgs extends BaseSyncArgs {
    /**
     * Spectra container image
     */
    image?: pulumi.Input<string>;

    /**
     * Resource group name
     */
    resourceGroupName: pulumi.Input<string>;

    /**
     * Azure location
     */
    location?: pulumi.Input<string>;

    /**
     * CPU cores for the container
     */
    cpu?: pulumi.Input<number>;

    /**
     * Memory in GB for the container
     */
    memoryInGb?: pulumi.Input<number>;
}

/**
 * ContainerInstanceSync creates an Azure Container Instance for running Spectra syncs
 *
 * Note: This is a placeholder implementation. Full implementation requires
 * @pulumi/azure-native package to be available.
 */
export class ContainerInstanceSync extends pulumi.ComponentResource implements SyncOutputs {
    public readonly name: pulumi.Output<string>;
    public readonly arn?: pulumi.Output<string>;
    public readonly logGroupName?: pulumi.Output<string>;
    public readonly secretArn?: pulumi.Output<string>;

    constructor(
        name: string,
        args: ContainerInstanceSyncArgs,
        opts?: pulumi.ComponentResourceOptions
    ) {
        super("spectra:azure:ContainerInstanceSync", name, {}, opts);

        const tags = mergeTags(args.tags as Record<string, string>);

        // Note: Full implementation would use @pulumi/azure-native
        // This is a placeholder showing the structure

        this.name = pulumi.output(name);

        this.registerOutputs({
            name: this.name,
        });
    }
}
