/**
 * Tree view provider for md2jira stories
 * 
 * Shows stories in the explorer sidebar.
 */

import * as vscode from 'vscode';

interface StoryItem {
    id: string;
    title: string;
    line: number;
    status?: string;
}

export class StoryTreeDataProvider implements vscode.TreeDataProvider<StoryTreeItem> {
    private _onDidChangeTreeData: vscode.EventEmitter<StoryTreeItem | undefined | null | void> = 
        new vscode.EventEmitter<StoryTreeItem | undefined | null | void>();
    readonly onDidChangeTreeData: vscode.Event<StoryTreeItem | undefined | null | void> = 
        this._onDidChangeTreeData.event;

    constructor() {
        // Refresh on editor change
        vscode.window.onDidChangeActiveTextEditor(() => {
            this.refresh();
        });

        // Refresh on document change
        vscode.workspace.onDidChangeTextDocument(() => {
            this.refresh();
        });
    }

    refresh(): void {
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: StoryTreeItem): vscode.TreeItem {
        return element;
    }

    getChildren(element?: StoryTreeItem): Thenable<StoryTreeItem[]> {
        if (element) {
            // No children for stories
            return Promise.resolve([]);
        }

        const editor = vscode.window.activeTextEditor;
        if (!editor || editor.document.languageId !== 'markdown') {
            return Promise.resolve([]);
        }

        const stories = this.parseStories(editor.document);
        return Promise.resolve(
            stories.map(story => new StoryTreeItem(story, editor.document.uri))
        );
    }

    private parseStories(document: vscode.TextDocument): StoryItem[] {
        const stories: StoryItem[] = [];
        const text = document.getText();
        const lines = text.split('\n');

        const storyPattern = /^###\s+([📋✅🔄⏸️]*)\s*([A-Z]+-\d+):\s*(.+)/;

        for (let i = 0; i < lines.length; i++) {
            const match = lines[i].match(storyPattern);
            if (match) {
                const emoji = match[1];
                let status: string | undefined;

                if (emoji.includes('✅')) {
                    status = 'done';
                } else if (emoji.includes('🔄')) {
                    status = 'in_progress';
                } else if (emoji.includes('⏸️')) {
                    status = 'blocked';
                }

                stories.push({
                    id: match[2],
                    title: match[3].trim(),
                    line: i + 1,
                    status
                });
            }
        }

        return stories;
    }
}

class StoryTreeItem extends vscode.TreeItem {
    constructor(
        public readonly story: StoryItem,
        public readonly documentUri: vscode.Uri
    ) {
        super(story.id, vscode.TreeItemCollapsibleState.None);

        this.description = story.title;
        this.tooltip = `${story.id}: ${story.title}`;

        // Icon based on status
        switch (story.status) {
            case 'done':
                this.iconPath = new vscode.ThemeIcon('check', new vscode.ThemeColor('terminal.ansiGreen'));
                break;
            case 'in_progress':
                this.iconPath = new vscode.ThemeIcon('sync', new vscode.ThemeColor('terminal.ansiBlue'));
                break;
            case 'blocked':
                this.iconPath = new vscode.ThemeIcon('circle-slash', new vscode.ThemeColor('terminal.ansiRed'));
                break;
            default:
                this.iconPath = new vscode.ThemeIcon('circle-outline');
        }

        // Command to jump to story
        this.command = {
            command: 'vscode.open',
            title: 'Go to Story',
            arguments: [
                documentUri,
                {
                    selection: new vscode.Range(story.line - 1, 0, story.line - 1, 0)
                }
            ]
        };
    }
}

