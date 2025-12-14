/**
 * CodeLens provider for md2jira stories
 * 
 * Shows action buttons above each story header.
 */

import * as vscode from 'vscode';

export class StoryCodeLensProvider implements vscode.CodeLensProvider {
    private _onDidChangeCodeLenses: vscode.EventEmitter<void> = new vscode.EventEmitter<void>();
    public readonly onDidChangeCodeLenses: vscode.Event<void> = this._onDidChangeCodeLenses.event;

    constructor() {
        // Refresh on document change
        vscode.workspace.onDidChangeTextDocument(() => {
            this._onDidChangeCodeLenses.fire();
        });
    }

    provideCodeLenses(document: vscode.TextDocument): vscode.CodeLens[] {
        const codeLenses: vscode.CodeLens[] = [];
        const text = document.getText();
        const lines = text.split('\n');

        // Pattern for story headers
        const storyPattern = /^###\s+[📋✅🔄⏸️]*\s*([A-Z]+-\d+):\s*(.+)/;
        // Pattern for epic headers
        const epicPattern = /^#\s+[🚀]*\s*([A-Z][A-Z0-9]+-\d+):\s*(.+)/;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const range = new vscode.Range(i, 0, i, line.length);

            // Check for story header
            const storyMatch = line.match(storyPattern);
            if (storyMatch) {
                const storyId = storyMatch[1];

                // Copy ID lens
                codeLenses.push(new vscode.CodeLens(range, {
                    title: '$(copy) Copy ID',
                    command: 'md2jira.copyStoryId',
                    tooltip: `Copy ${storyId} to clipboard`
                }));

                // Open in Jira lens
                codeLenses.push(new vscode.CodeLens(range, {
                    title: '$(link-external) Open in Jira',
                    command: 'md2jira.openInJira',
                    tooltip: `Open ${storyId} in Jira`
                }));

                continue;
            }

            // Check for epic header
            const epicMatch = line.match(epicPattern);
            if (epicMatch) {
                const epicId = epicMatch[1];

                // Sync lens
                codeLenses.push(new vscode.CodeLens(range, {
                    title: '$(sync) Sync',
                    command: 'md2jira.sync',
                    tooltip: 'Sync to Jira (dry-run)'
                }));

                // Validate lens
                codeLenses.push(new vscode.CodeLens(range, {
                    title: '$(check) Validate',
                    command: 'md2jira.validate',
                    tooltip: 'Validate markdown'
                }));

                // Open in Jira lens
                codeLenses.push(new vscode.CodeLens(range, {
                    title: '$(link-external) Open Epic',
                    command: 'md2jira.openInJira',
                    tooltip: `Open ${epicId} in Jira`
                }));
            }
        }

        return codeLenses;
    }
}

