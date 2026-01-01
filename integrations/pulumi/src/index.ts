// Copyright (c) spectra
// SPDX-License-Identifier: MIT

/**
 * Spectra Pulumi Provider
 *
 * Deploy and manage Spectra syncs across multiple cloud platforms.
 */

// Core types
export * from "./types";

// AWS resources
export * as aws from "./aws";

// Azure resources
export * as azure from "./azure";

// GCP resources
export * as gcp from "./gcp";

// Kubernetes resources
export * as kubernetes from "./kubernetes";

// Utilities
export * from "./utils";
