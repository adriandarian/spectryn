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
    mergeTags,
    credentialsToSecretJson,
} from "../utils";

/**
 * AWS Lambda sync arguments
 */
export interface LambdaSyncArgs extends BaseSyncArgs {
    /**
     * Spectra container image for Lambda
     */
    image?: pulumi.Input<string>;

    /**
     * Lambda function timeout in seconds
     */
    timeout?: pulumi.Input<number>;

    /**
     * Lambda function memory in MB
     */
    memorySize?: pulumi.Input<number>;
}

/**
 * LambdaSync creates an AWS Lambda function for running Spectra syncs
 */
export class LambdaSync extends pulumi.ComponentResource implements SyncOutputs {
    public readonly name: pulumi.Output<string>;
    public readonly arn: pulumi.Output<string>;
    public readonly logGroupName: pulumi.Output<string>;
    public readonly secretArn: pulumi.Output<string>;

    public readonly function: aws.lambda.Function;
    public readonly secret: aws.secretsmanager.Secret;
    public readonly logGroup: aws.cloudwatch.LogGroup;
    public readonly schedule?: aws.cloudwatch.EventRule;

    constructor(
        name: string,
        args: LambdaSyncArgs,
        opts?: pulumi.ComponentResourceOptions
    ) {
        super("spectra:aws:LambdaSync", name, {}, opts);

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

        new aws.secretsmanager.SecretVersion(
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

        // Create IAM role
        const role = new aws.iam.Role(
            `${name}-role`,
            {
                name: `spectra-${name}-lambda`,
                assumeRolePolicy: JSON.stringify({
                    Version: "2012-10-17",
                    Statement: [
                        {
                            Effect: "Allow",
                            Principal: { Service: "lambda.amazonaws.com" },
                            Action: "sts:AssumeRole",
                        },
                    ],
                }),
                tags,
            },
            defaultOpts
        );

        new aws.iam.RolePolicyAttachment(
            `${name}-basic-policy`,
            {
                role: role.name,
                policyArn:
                    "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            },
            defaultOpts
        );

        new aws.iam.RolePolicy(
            `${name}-secrets-policy`,
            {
                role: role.id,
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

        // Build environment variables
        const envVars = trackerToEnvVars(args.tracker);

        // Create Lambda function
        const image = args.image ?? "spectra/spectra:latest";

        this.function = new aws.lambda.Function(
            `${name}-function`,
            {
                name: `spectra-${name}`,
                packageType: "Image",
                imageUri: image,
                role: role.arn,
                timeout: args.timeout ?? 300,
                memorySize: args.memorySize ?? 1024,
                environment: {
                    variables: {
                        ...Object.fromEntries(
                            Object.entries(envVars).map(([k, v]) => [k, v as string])
                        ),
                        SECRETS_ARN: this.secret.arn as unknown as string,
                        DRY_RUN: args.dryRun ? "true" : "false",
                    },
                },
                tags,
            },
            defaultOpts
        );

        // Create log group
        this.logGroup = new aws.cloudwatch.LogGroup(
            `${name}-logs`,
            {
                name: pulumi.interpolate`/aws/lambda/${this.function.name}`,
                retentionInDays: args.monitoring?.logRetentionDays ?? 30,
                tags,
            },
            defaultOpts
        );

        // Create schedule if provided
        if (args.schedule) {
            this.schedule = new aws.cloudwatch.EventRule(
                `${name}-schedule`,
                {
                    name: `spectra-${name}-schedule`,
                    scheduleExpression: args.schedule as string,
                    tags,
                },
                defaultOpts
            );

            new aws.cloudwatch.EventTarget(
                `${name}-target`,
                {
                    rule: this.schedule.name,
                    arn: this.function.arn,
                },
                defaultOpts
            );

            new aws.lambda.Permission(
                `${name}-permission`,
                {
                    action: "lambda:InvokeFunction",
                    function: this.function.name,
                    principal: "events.amazonaws.com",
                    sourceArn: this.schedule.arn,
                },
                defaultOpts
            );
        }

        // Set outputs
        this.name = pulumi.output(name);
        this.arn = this.function.arn;
        this.logGroupName = this.logGroup.name;
        this.secretArn = this.secret.arn;

        this.registerOutputs({
            name: this.name,
            arn: this.arn,
            logGroupName: this.logGroupName,
            secretArn: this.secretArn,
        });
    }
}
