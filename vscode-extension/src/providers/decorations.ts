/**
 * Decoration provider for md2jira stories
 * 
 * Highlights story IDs and shows inline status.
 */

import * as vscode from 'vscode';

export class StoryDecorationProvider implements vscode.Disposable {
    private storyDecorationType: vscode.TextEditorDecorationType;
    private epicDecorationType: vscode.TextEditorDecorationType;
    private statusDecorationTypes: Map<string, vscode.TextEditorDecorationType>;
    private disposables: vscode.Disposable[] = [];

    constructor() {
        // Story ID decoration
        this.storyDecorationType = vscode.window.createTextEditorDecorationType({
            color: new vscode.ThemeColor('md2jira.storyIdColor'),
            fontWeight: 'bold',
        });

        // Epic ID decoration
        this.epicDecorationType = vscode.window.createTextEditorDecorationType({
            color: new vscode.ThemeColor('md2jira.epicIdColor'),
            fontWeight: 'bold',
        });

        // Status decorations
        this.statusDecorationTypes = new Map([
            ['done', vscode.window.createTextEditorDecorationType({
                after: {
                    contentText: ' ✓',
                    color: new vscode.ThemeColor('terminal.ansiGreen'),
                }
            })],
            ['in_progress', vscode.window.createTextEditorDecorationType({
                after: {
                    contentText: ' ⟳',
                    color: new vscode.ThemeColor('terminal.ansiBlue'),
                }
            })],
            ['blocked', vscode.window.createTextEditorDecorationType({
                after: {
                    contentText: ' ⊘',
                    color: new vscode.ThemeColor('terminal.ansiRed'),
                }
            })],
        ]);

        // Update decorations on editor change
        this.disposables.push(
            vscode.window.onDidChangeActiveTextEditor(editor => {
                if (editor) {
                    this.updateDecorations(editor);
                }
            })
        );

        // Update decorations on document change
        this.disposables.push(
            vscode.workspace.onDidChangeTextDocument(event => {
                const editor = vscode.window.activeTextEditor;
                if (editor && event.document === editor.document) {
                    this.updateDecorations(editor);
                }
            })
        );

        // Initial update
        if (vscode.window.activeTextEditor) {
            this.updateDecorations(vscode.window.activeTextEditor);
        }
    }

    updateDecorations(editor: vscode.TextEditor): void {
        if (editor.document.languageId !== 'markdown') {
            return;
        }

        const text = editor.document.getText();
        const lines = text.split('\n');

        const storyDecorations: vscode.DecorationOptions[] = [];
        const epicDecorations: vscode.DecorationOptions[] = [];
        const statusDecorations: Map<string, vscode.DecorationOptions[]> = new Map([
            ['done', []],
            ['in_progress', []],
            ['blocked', []],
        ]);

        // Pattern for story IDs in headers
        const storyPattern = /^###\s+([📋✅🔄⏸️]*)\s*([A-Z]+-\d+):/;
        // Pattern for epic IDs
        const epicPattern = /^#\s+[🚀]*\s*([A-Z][A-Z0-9]+-\d+):/;

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];

            // Check for story header
            const storyMatch = line.match(storyPattern);
            if (storyMatch) {
                const emoji = storyMatch[1];
                const storyId = storyMatch[2];
                const startIndex = line.indexOf(storyId);
                const range = new vscode.Range(i, startIndex, i, startIndex + storyId.length);

                storyDecorations.push({ range });

                // Detect status from emoji
                if (emoji.includes('✅')) {
                    statusDecorations.get('done')?.push({
                        range: new vscode.Range(i, line.length, i, line.length)
                    });
                } else if (emoji.includes('🔄')) {
                    statusDecorations.get('in_progress')?.push({
                        range: new vscode.Range(i, line.length, i, line.length)
                    });
                } else if (emoji.includes('⏸️')) {
                    statusDecorations.get('blocked')?.push({
                        range: new vscode.Range(i, line.length, i, line.length)
                    });
                }

                continue;
            }

            // Check for epic header
            const epicMatch = line.match(epicPattern);
            if (epicMatch) {
                const epicId = epicMatch[1];
                const startIndex = line.indexOf(epicId);
                const range = new vscode.Range(i, startIndex, i, startIndex + epicId.length);

                epicDecorations.push({ range });
            }
        }

        // Apply decorations
        editor.setDecorations(this.storyDecorationType, storyDecorations);
        editor.setDecorations(this.epicDecorationType, epicDecorations);

        for (const [status, decorations] of statusDecorations) {
            const decorationType = this.statusDecorationTypes.get(status);
            if (decorationType) {
                editor.setDecorations(decorationType, decorations);
            }
        }
    }

    dispose(): void {
        this.storyDecorationType.dispose();
        this.epicDecorationType.dispose();
        for (const decorationType of this.statusDecorationTypes.values()) {
            decorationType.dispose();
        }
        for (const disposable of this.disposables) {
            disposable.dispose();
        }
    }
}

