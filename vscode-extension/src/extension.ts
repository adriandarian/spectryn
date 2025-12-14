/**
 * md2jira VS Code Extension
 * 
 * Provides integration with md2jira CLI for syncing markdown with Jira.
 */

import * as vscode from 'vscode';
import * as cp from 'child_process';
import * as path from 'path';

// Providers
import { StoryCodeLensProvider } from './providers/codeLens';
import { StoryDecorationProvider } from './providers/decorations';
import { StoryTreeDataProvider } from './providers/treeView';
import { DiagnosticsProvider } from './providers/diagnostics';

// Types
interface Story {
    id: string;
    title: string;
    line: number;
    status?: string;
    points?: number;
}

interface Epic {
    id: string;
    title: string;
    line: number;
}

interface Md2JiraResult {
    code: number;
    stdout: string;
    stderr: string;
}

// Extension state
let statusBarItem: vscode.StatusBarItem;
let outputChannel: vscode.OutputChannel;
let diagnosticsProvider: DiagnosticsProvider;

/**
 * Extension activation
 */
export function activate(context: vscode.ExtensionContext) {
    console.log('md2jira extension activated');

    // Create output channel
    outputChannel = vscode.window.createOutputChannel('md2jira');

    // Create status bar item
    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
    );
    statusBarItem.command = 'md2jira.gotoStory';
    context.subscriptions.push(statusBarItem);

    // Create diagnostics provider
    diagnosticsProvider = new DiagnosticsProvider();
    context.subscriptions.push(diagnosticsProvider);

    // Register commands
    registerCommands(context);

    // Register providers
    registerProviders(context);

    // Register event handlers
    registerEventHandlers(context);

    // Update status bar for current editor
    updateStatusBar();
}

/**
 * Extension deactivation
 */
export function deactivate() {
    console.log('md2jira extension deactivated');
}

/**
 * Register all commands
 */
function registerCommands(context: vscode.ExtensionContext) {
    // Validate command
    context.subscriptions.push(
        vscode.commands.registerCommand('md2jira.validate', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor || editor.document.languageId !== 'markdown') {
                vscode.window.showWarningMessage('Open a markdown file to validate');
                return;
            }

            await runValidate(editor.document);
        })
    );

    // Sync (dry-run) command
    context.subscriptions.push(
        vscode.commands.registerCommand('md2jira.sync', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor || editor.document.languageId !== 'markdown') {
                vscode.window.showWarningMessage('Open a markdown file to sync');
                return;
            }

            const epic = await getEpicKey(editor.document);
            if (!epic) return;

            await runSync(editor.document, epic, false);
        })
    );

    // Sync (execute) command
    context.subscriptions.push(
        vscode.commands.registerCommand('md2jira.syncExecute', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor || editor.document.languageId !== 'markdown') {
                vscode.window.showWarningMessage('Open a markdown file to sync');
                return;
            }

            const epic = await getEpicKey(editor.document);
            if (!epic) return;

            const confirm = await vscode.window.showWarningMessage(
                `Sync to ${epic}? This will make changes in Jira.`,
                'Yes, Execute',
                'Cancel'
            );

            if (confirm === 'Yes, Execute') {
                await runSync(editor.document, epic, true);
            }
        })
    );

    // Dashboard command
    context.subscriptions.push(
        vscode.commands.registerCommand('md2jira.dashboard', async () => {
            const editor = vscode.window.activeTextEditor;
            const args = ['--dashboard'];

            if (editor?.document.languageId === 'markdown') {
                args.push('--markdown', editor.document.uri.fsPath);
                const epic = detectEpic(editor.document);
                if (epic) {
                    args.push('--epic', epic);
                }
            }

            const result = await runMd2Jira(args);
            showResultPanel('md2jira Dashboard', result.stdout);
        })
    );

    // Init command
    context.subscriptions.push(
        vscode.commands.registerCommand('md2jira.init', async () => {
            const terminal = vscode.window.createTerminal('md2jira init');
            terminal.show();
            terminal.sendText(getExecutable() + ' --init');
        })
    );

    // Generate command
    context.subscriptions.push(
        vscode.commands.registerCommand('md2jira.generate', async () => {
            const epicKey = await vscode.window.showInputBox({
                prompt: 'Enter Jira Epic Key',
                placeHolder: 'PROJ-123'
            });

            if (!epicKey) return;

            const result = await runMd2Jira(['--generate', '--epic', epicKey]);
            if (result.code === 0) {
                vscode.window.showInformationMessage('Template generated successfully');
                showResultPanel('Generated Template', result.stdout);
            } else {
                vscode.window.showErrorMessage('Failed to generate template');
                outputChannel.append(result.stderr);
            }
        })
    );

    // Go to story command
    context.subscriptions.push(
        vscode.commands.registerCommand('md2jira.gotoStory', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor || editor.document.languageId !== 'markdown') {
                return;
            }

            const stories = parseStories(editor.document);
            if (stories.length === 0) {
                vscode.window.showInformationMessage('No stories found in this file');
                return;
            }

            const items = stories.map(s => ({
                label: s.id,
                description: s.title,
                detail: s.status ? `Status: ${s.status}` : undefined,
                story: s
            }));

            const selected = await vscode.window.showQuickPick(items, {
                placeHolder: 'Select a story to jump to'
            });

            if (selected) {
                const position = new vscode.Position(selected.story.line - 1, 0);
                editor.selection = new vscode.Selection(position, position);
                editor.revealRange(
                    new vscode.Range(position, position),
                    vscode.TextEditorRevealType.InCenter
                );
            }
        })
    );

    // Copy story ID command
    context.subscriptions.push(
        vscode.commands.registerCommand('md2jira.copyStoryId', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;

            const story = getStoryAtLine(editor.document, editor.selection.active.line);
            if (story) {
                await vscode.env.clipboard.writeText(story.id);
                vscode.window.showInformationMessage(`Copied: ${story.id}`);
            }
        })
    );

    // Open in Jira command
    context.subscriptions.push(
        vscode.commands.registerCommand('md2jira.openInJira', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;

            const config = vscode.workspace.getConfiguration('md2jira');
            const jiraUrl = config.get<string>('jiraUrl');

            if (!jiraUrl) {
                const url = await vscode.window.showInputBox({
                    prompt: 'Enter your Jira URL',
                    placeHolder: 'https://your-org.atlassian.net'
                });
                if (url) {
                    await config.update('jiraUrl', url, vscode.ConfigurationTarget.Global);
                }
                return;
            }

            const story = getStoryAtLine(editor.document, editor.selection.active.line);
            if (story) {
                const issueUrl = `${jiraUrl}/browse/${story.id}`;
                vscode.env.openExternal(vscode.Uri.parse(issueUrl));
            }
        })
    );
}

/**
 * Register providers
 */
function registerProviders(context: vscode.ExtensionContext) {
    const config = vscode.workspace.getConfiguration('md2jira');

    // CodeLens provider
    if (config.get<boolean>('showCodeLens')) {
        context.subscriptions.push(
            vscode.languages.registerCodeLensProvider(
                { language: 'markdown' },
                new StoryCodeLensProvider()
            )
        );
    }

    // Tree view provider
    const treeDataProvider = new StoryTreeDataProvider();
    context.subscriptions.push(
        vscode.window.registerTreeDataProvider('md2jiraStories', treeDataProvider)
    );

    // Decoration provider
    if (config.get<boolean>('showStoryDecorations')) {
        const decorationProvider = new StoryDecorationProvider();
        context.subscriptions.push(decorationProvider);
    }
}

/**
 * Register event handlers
 */
function registerEventHandlers(context: vscode.ExtensionContext) {
    const config = vscode.workspace.getConfiguration('md2jira');

    // Update status bar on editor change
    context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(() => {
            updateStatusBar();
        })
    );

    // Update status bar on document change
    context.subscriptions.push(
        vscode.workspace.onDidChangeTextDocument((e) => {
            if (e.document === vscode.window.activeTextEditor?.document) {
                updateStatusBar();
            }
        })
    );

    // Auto-validate on save
    if (config.get<boolean>('autoValidate')) {
        context.subscriptions.push(
            vscode.workspace.onDidSaveTextDocument(async (document) => {
                if (document.languageId === 'markdown') {
                    await runValidate(document, true);
                }
            })
        );
    }
}

/**
 * Run md2jira validate
 */
async function runValidate(document: vscode.TextDocument, silent: boolean = false): Promise<void> {
    const args = ['--validate', '--markdown', document.uri.fsPath];

    if (!silent) {
        vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: 'Validating markdown...',
            cancellable: false
        }, async () => {
            const result = await runMd2Jira(args);
            diagnosticsProvider.updateDiagnostics(document, result);

            if (result.code === 0) {
                vscode.window.showInformationMessage('✓ Validation passed');
            } else {
                vscode.window.showErrorMessage('✗ Validation failed');
                showResultPanel('Validation Results', result.stdout);
            }
        });
    } else {
        const result = await runMd2Jira(args);
        diagnosticsProvider.updateDiagnostics(document, result);
    }
}

/**
 * Run md2jira sync
 */
async function runSync(document: vscode.TextDocument, epicKey: string, execute: boolean): Promise<void> {
    const args = ['--markdown', document.uri.fsPath, '--epic', epicKey];

    if (execute) {
        args.push('--execute', '--no-confirm');
    }

    vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: execute ? 'Syncing to Jira...' : 'Running dry-run sync...',
        cancellable: false
    }, async () => {
        const result = await runMd2Jira(args);

        if (result.code === 0) {
            const msg = execute ? '✓ Sync completed' : '✓ Dry-run completed';
            vscode.window.showInformationMessage(msg);
        } else {
            vscode.window.showErrorMessage('✗ Sync failed');
        }

        showResultPanel('Sync Results', result.stdout);
    });
}

/**
 * Get or prompt for epic key
 */
async function getEpicKey(document: vscode.TextDocument): Promise<string | undefined> {
    let epic = detectEpic(document);

    if (!epic) {
        epic = await vscode.window.showInputBox({
            prompt: 'Enter Jira Epic Key',
            placeHolder: 'PROJ-123'
        });
    }

    return epic;
}

/**
 * Detect epic key from document
 */
function detectEpic(document: vscode.TextDocument): string | undefined {
    const text = document.getText();
    const match = text.match(/([A-Z][A-Z0-9]+-\d+)/);
    return match ? match[1] : undefined;
}

/**
 * Parse stories from document
 */
function parseStories(document: vscode.TextDocument): Story[] {
    const stories: Story[] = [];
    const text = document.getText();
    const lines = text.split('\n');

    // Pattern: ### 📋 US-001: Title or ### US-001: Title
    const storyPattern = /^###\s+[📋✅🔄⏸️]*\s*([A-Z]+-\d+):\s*(.+)/;

    for (let i = 0; i < lines.length; i++) {
        const match = lines[i].match(storyPattern);
        if (match) {
            stories.push({
                id: match[1],
                title: match[2].trim(),
                line: i + 1
            });
        }
    }

    return stories;
}

/**
 * Get story at specific line
 */
function getStoryAtLine(document: vscode.TextDocument, line: number): Story | undefined {
    const stories = parseStories(document);

    // Find the story that contains this line
    for (let i = stories.length - 1; i >= 0; i--) {
        if (stories[i].line - 1 <= line) {
            return stories[i];
        }
    }

    return undefined;
}

/**
 * Update status bar
 */
function updateStatusBar(): void {
    const config = vscode.workspace.getConfiguration('md2jira');
    if (!config.get<boolean>('showStatusBar')) {
        statusBarItem.hide();
        return;
    }

    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== 'markdown') {
        statusBarItem.hide();
        return;
    }

    const stories = parseStories(editor.document);
    const epic = detectEpic(editor.document);

    if (stories.length > 0) {
        statusBarItem.text = `$(list-unordered) ${stories.length} stories`;
        if (epic) {
            statusBarItem.text += ` (${epic})`;
        }
        statusBarItem.tooltip = 'Click to jump to a story';
        statusBarItem.show();
    } else {
        statusBarItem.hide();
    }
}

/**
 * Run md2jira CLI command
 */
function runMd2Jira(args: string[]): Promise<Md2JiraResult> {
    return new Promise((resolve) => {
        const executable = getExecutable();
        const cmd = [executable, ...args].join(' ');

        outputChannel.appendLine(`> ${cmd}`);

        cp.exec(cmd, { maxBuffer: 1024 * 1024 }, (error, stdout, stderr) => {
            outputChannel.appendLine(stdout);
            if (stderr) {
                outputChannel.appendLine(stderr);
            }

            resolve({
                code: error ? error.code || 1 : 0,
                stdout: stdout || '',
                stderr: stderr || ''
            });
        });
    });
}

/**
 * Get md2jira executable path
 */
function getExecutable(): string {
    const config = vscode.workspace.getConfiguration('md2jira');
    return config.get<string>('executable') || 'md2jira';
}

/**
 * Show result in a panel
 */
function showResultPanel(title: string, content: string): void {
    const panel = vscode.window.createWebviewPanel(
        'md2jiraResult',
        title,
        vscode.ViewColumn.Beside,
        {}
    );

    panel.webview.html = `
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    font-family: var(--vscode-font-family);
                    padding: 20px;
                    color: var(--vscode-foreground);
                    background: var(--vscode-editor-background);
                }
                pre {
                    white-space: pre-wrap;
                    word-wrap: break-word;
                    font-family: var(--vscode-editor-font-family);
                    font-size: var(--vscode-editor-font-size);
                    line-height: 1.5;
                }
                .success { color: var(--vscode-terminal-ansiGreen); }
                .error { color: var(--vscode-terminal-ansiRed); }
                .warning { color: var(--vscode-terminal-ansiYellow); }
            </style>
        </head>
        <body>
            <pre>${escapeHtml(content)}</pre>
        </body>
        </html>
    `;
}

/**
 * Escape HTML
 */
function escapeHtml(text: string): string {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Export for testing
export { parseStories, detectEpic, getStoryAtLine };

