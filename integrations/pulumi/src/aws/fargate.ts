// Copyright (c) spectra
// SPDX-License-Identifier: MIT

import * as pulumi from "@pulumi/pulumi";
import * as aws from "@pulumi/aws";
import {
    BaseSyncArgs,
    SyncOutputs,
} from "../types";
import {
    trackerToEnvVars,
    buildSpectraArgs,
    mergeTags,
    credentialsToSecretJson,
} from "../utils";

/**
 * AWS Fargate sync arguments
 */
export interface FargateSyncArgs extends BaseSyncArgs {
    /**
     * Spectra container image
     */
    image?: pulumi.Input<string>;

    /**
     * VPC ID (creates new if not provided)
     */
    vpcId?: pulumi.Input<string>;

    /**
     * Subnet IDs for Fargate tasks
     */
    subnetIds?: pulumi.Input<string>[];

    /**
     * CPU units for the task (256, 512, 1024, 2048, 4096)
     */
    cpu?: pulumi.Input<string>;

    /**
     * Memory in MB for the task
     */
    memory?: pulumi.Input<string>;
}

/**
 * FargateSync creates an ECS Fargate task for running Spectra syncs
 */
export class FargateSync extends pulumi.ComponentResource implements SyncOutputs {
    public readonly name: pulumi.Output<string>;
    public readonly arn: pulumi.Output<string>;
    public readonly logGroupName: pulumi.Output<string>;
    public readonly secretArn: pulumi.Output<string>;
    public readonly dashboardUrl?: pulumi.Output<string>;

    public readonly cluster: aws.ecs.Cluster;
    public readonly taskDefinition: aws.ecs.TaskDefinition;
    public readonly secret: aws.secretsmanager.Secret;
    public readonly logGroup: aws.cloudwatch.LogGroup;

    constructor(
        name: string,
        args: FargateSyncArgs,
        opts?: pulumi.ComponentResourceOptions
    ) {
        super("spectra:aws:FargateSync", name, {}, opts);

        const defaultOpts = { parent: this };
        const tags = mergeTags(args.tags as Record<string, string>);

        // Create secrets manager secret
        this.secret = new aws.secretsmanager.Secret(
            `${name}-credentials`,
            {
                name: `spectra/${name}/credentials`,
                tags,
            },
            defaultOpts
        );

        const secretVersion = new aws.secretsmanager.SecretVersion(
            `${name}-credentials-version`,
            {
                secretId: this.secret.id,
                secretString: credentialsToSecretJson(
                    args.tracker.credentials,
                    args.tracker.type
                ),
            },
            defaultOpts
        );

        // Create log group
        this.logGroup = new aws.cloudwatch.LogGroup(
            `${name}-logs`,
            {
                name: `/ecs/spectra/${name}`,
                retentionInDays: args.monitoring?.logRetentionDays ?? 30,
                tags,
            },
            defaultOpts
        );

        // Create ECS cluster
        this.cluster = new aws.ecs.Cluster(
            `${name}-cluster`,
            {
                name: `spectra-${name}`,
                settings: [
                    {
                        name: "containerInsights",
                        value: args.monitoring?.enabled ? "enabled" : "disabled",
                    },
                ],
                tags,
            },
            defaultOpts
        );

        // Create task execution role
        const executionRole = new aws.iam.Role(
            `${name}-execution-role`,
            {
                name: `spectra-${name}-execution`,
                assumeRolePolicy: JSON.stringify({
                    Version: "2012-10-17",
                    Statement: [
                        {
                            Effect: "Allow",
                            Principal: { Service: "ecs-tasks.amazonaws.com" },
                            Action: "sts:AssumeRole",
                        },
                    ],
                }),
                tags,
            },
            defaultOpts
        );

        new aws.iam.RolePolicyAttachment(
            `${name}-execution-policy`,
            {
                role: executionRole.name,
                policyArn:
                    "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
            },
            defaultOpts
        );

        // Policy for secrets access
        new aws.iam.RolePolicy(
            `${name}-secrets-policy`,
            {
                role: executionRole.id,
                policy: this.secret.arn.apply((arn) =>
                    JSON.stringify({
                        Version: "2012-10-17",
                        Statement: [
                            {
                                Effect: "Allow",
                                Action: ["secretsmanager:GetSecretValue"],
                                Resource: arn,
                            },
                        ],
                    })
                ),
            },
            defaultOpts
        );

        // Create task role
        const taskRole = new aws.iam.Role(
            `${name}-task-role`,
            {
                name: `spectra-${name}-task`,
                assumeRolePolicy: JSON.stringify({
                    Version: "2012-10-17",
                    Statement: [
                        {
                            Effect: "Allow",
                            Principal: { Service: "ecs-tasks.amazonaws.com" },
                            Action: "sts:AssumeRole",
                        },
                    ],
                }),
                tags,
            },
            defaultOpts
        );

        // Build environment variables
        const envVars = trackerToEnvVars(args.tracker);

        // Create task definition
        const image = args.image ?? "spectra/spectra:latest";
        const command = buildSpectraArgs(args.tracker, {
            markdownPath: "/data/spec.md",
            dryRun: args.dryRun,
            phases: args.phases as string[],
            incremental: args.incremental,
        });

        this.taskDefinition = new aws.ecs.TaskDefinition(
            `${name}-task`,
            {
                family: `spectra-${name}`,
                networkMode: "awsvpc",
                requiresCompatibilities: ["FARGATE"],
                cpu: args.cpu ?? "512",
                memory: args.memory ?? "1024",
                executionRoleArn: executionRole.arn,
                taskRoleArn: taskRole.arn,
                containerDefinitions: pulumi
                    .all([this.secret.arn, this.logGroup.name])
                    .apply(([secretArn, logGroupName]) =>
                        JSON.stringify([
                            {
                                name: "spectra",
                                image: image,
                                essential: true,
                                command: command,
                                environment: Object.entries(envVars)
                                    .filter(([key]) => !key.includes("TOKEN") && !key.includes("KEY"))
                                    .map(([name, value]) => ({ name, value })),
                                secrets: [
                                    {
                                        name: "CREDENTIALS_JSON",
                                        valueFrom: secretArn,
                                    },
                                ],
                                logConfiguration: {
                                    logDriver: "awslogs",
                                    options: {
                                        "awslogs-group": logGroupName,
                                        "awslogs-region": aws.getRegion().then(r => r.name),
                                        "awslogs-stream-prefix": "spectra",
                                    },
                                },
                            },
                        ])
                    ),
                tags,
            },
            defaultOpts
        );

        // Set outputs
        this.name = pulumi.output(name);
        this.arn = this.taskDefinition.arn;
        this.logGroupName = this.logGroup.name;
        this.secretArn = this.secret.arn;

        // Register outputs
        this.registerOutputs({
            name: this.name,
            arn: this.arn,
            logGroupName: this.logGroupName,
            secretArn: this.secretArn,
        });
    }
}
