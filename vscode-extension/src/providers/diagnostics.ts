/**
 * Diagnostics provider for md2jira validation
 * 
 * Shows validation errors and warnings in the Problems panel.
 */

import * as vscode from 'vscode';

interface Md2JiraResult {
    code: number;
    stdout: string;
    stderr: string;
}

export class DiagnosticsProvider implements vscode.Disposable {
    private diagnosticCollection: vscode.DiagnosticCollection;

    constructor() {
        this.diagnosticCollection = vscode.languages.createDiagnosticCollection('md2jira');
    }

    /**
     * Update diagnostics based on md2jira output
     */
    updateDiagnostics(document: vscode.TextDocument, result: Md2JiraResult): void {
        const diagnostics: vscode.Diagnostic[] = [];

        if (result.code !== 0) {
            // Parse validation output for errors
            const errorPatterns = [
                // Pattern: "Line 10: Missing story points"
                /Line\s+(\d+):\s*(.+)/g,
                // Pattern: "[ERR-001] Line 5: Invalid status"
                /\[(\w+-\d+)\]\s*Line\s+(\d+):\s*(.+)/g,
                // Pattern: "Error: Missing required field"
                /Error:\s*(.+)/g,
                // Pattern: "Warning: Short title"
                /Warning:\s*(.+)/g,
            ];

            const output = result.stdout + '\n' + result.stderr;

            // Try to parse structured errors
            for (const pattern of errorPatterns) {
                let match;
                while ((match = pattern.exec(output)) !== null) {
                    const diagnostic = this.parseDiagnostic(match, document);
                    if (diagnostic) {
                        diagnostics.push(diagnostic);
                    }
                }
            }

            // If no structured errors found, create a generic one
            if (diagnostics.length === 0 && result.code !== 0) {
                const diagnostic = new vscode.Diagnostic(
                    new vscode.Range(0, 0, 0, 0),
                    'Validation failed. Run md2jira --validate for details.',
                    vscode.DiagnosticSeverity.Error
                );
                diagnostic.source = 'md2jira';
                diagnostics.push(diagnostic);
            }
        }

        this.diagnosticCollection.set(document.uri, diagnostics);
    }

    /**
     * Parse a regex match into a diagnostic
     */
    private parseDiagnostic(
        match: RegExpExecArray, 
        document: vscode.TextDocument
    ): vscode.Diagnostic | null {
        let line = 0;
        let message = '';
        let code = '';
        let severity = vscode.DiagnosticSeverity.Error;

        // Determine pattern type based on match groups
        if (match.length === 3) {
            // Pattern: Line X: message
            line = parseInt(match[1], 10) - 1;
            message = match[2];
        } else if (match.length === 4) {
            // Pattern: [CODE] Line X: message
            code = match[1];
            line = parseInt(match[2], 10) - 1;
            message = match[3];
        } else if (match.length === 2) {
            // Pattern: Error/Warning: message
            message = match[1];
            if (match[0].toLowerCase().startsWith('warning')) {
                severity = vscode.DiagnosticSeverity.Warning;
            }
        }

        // Validate line number
        if (line < 0 || line >= document.lineCount) {
            line = 0;
        }

        // Get the range for the line
        const lineText = document.lineAt(line).text;
        const range = new vscode.Range(line, 0, line, lineText.length);

        const diagnostic = new vscode.Diagnostic(range, message, severity);
        diagnostic.source = 'md2jira';

        if (code) {
            diagnostic.code = code;
        }

        return diagnostic;
    }

    /**
     * Clear diagnostics for a document
     */
    clear(document: vscode.TextDocument): void {
        this.diagnosticCollection.delete(document.uri);
    }

    /**
     * Clear all diagnostics
     */
    clearAll(): void {
        this.diagnosticCollection.clear();
    }

    dispose(): void {
        this.diagnosticCollection.dispose();
    }
}

