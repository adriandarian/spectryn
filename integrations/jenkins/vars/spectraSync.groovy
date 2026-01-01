// Spectra Jenkins Shared Library
// Main sync function

def call(Map config = [:]) {
    // Required parameters
    def markdownFile = config.markdownFile
    if (!markdownFile) {
        error "markdownFile is required"
    }

    // Optional parameters with defaults
    def epicKey = config.epicKey ?: ''
    def tracker = config.tracker ?: 'jira'
    def jiraUrl = config.jiraUrl ?: env.JIRA_URL ?: ''
    def dryRun = config.dryRun ?: false
    def execute = config.execute ?: true
    def phase = config.phase ?: 'all'
    def incremental = config.incremental ?: false
    def multiEpic = config.multiEpic ?: false
    def epicFilter = config.epicFilter ?: ''
    def backup = config.backup ?: true
    def verbose = config.verbose ?: false
    def exportResults = config.exportResults ?: ''
    def pythonVersion = config.pythonVersion ?: '3.11'
    def spectraVersion = config.spectraVersion ?: 'latest'

    // Validate file exists
    if (!fileExists(markdownFile)) {
        error "Markdown file not found: ${markdownFile}"
    }

    // Validate epic key for non-multi-epic mode
    if (!epicKey && !multiEpic) {
        error "epicKey is required (unless using multiEpic mode)"
    }

    echo "🚀 Spectra Jenkins Sync"
    echo "======================="

    // Install spectra
    sh """
        pip install --upgrade pip
        if [ "${spectraVersion}" = "latest" ]; then
            pip install spectra
        else
            pip install spectra==${spectraVersion}
        fi
        spectra --version
    """

    // Build command
    def cmd = "spectra sync --markdown ${markdownFile} --tracker ${tracker}"

    // Add epic key if provided
    if (epicKey) {
        cmd += " --epic ${epicKey}"
    }

    // Execution mode
    if (dryRun) {
        echo "📋 Mode: Dry-run (no changes will be made)"
    } else if (execute) {
        cmd += " --execute --no-confirm"
        echo "⚡ Mode: Execute"
    }

    // Sync phase
    if (phase != 'all') {
        cmd += " --phase ${phase}"
        echo "📌 Phase: ${phase}"
    }

    // Incremental mode
    if (incremental) {
        cmd += " --incremental"
        echo "🔄 Incremental sync enabled"
    }

    // Multi-epic mode
    if (multiEpic) {
        cmd += " --multi-epic"
        echo "📚 Multi-epic mode enabled"
        if (epicFilter) {
            cmd += " --epic-filter ${epicFilter}"
        }
    }

    // Backup
    if (backup) {
        cmd += " --backup"
    }

    // Verbose
    if (verbose) {
        cmd += " --verbose"
    }

    // Export results
    if (exportResults) {
        cmd += " --export ${exportResults}"
    }

    echo ""
    echo "Running: ${cmd}"
    echo ""

    // Set environment variables based on tracker
    withEnv(getTrackerEnvVars(tracker, jiraUrl)) {
        // Try to use credentials if available
        def credentialsId = getCredentialsId(tracker)

        if (credentialsId) {
            withCredentials([usernamePassword(
                credentialsId: credentialsId,
                usernameVariable: getCredentialUserVar(tracker),
                passwordVariable: getCredentialPassVar(tracker)
            )]) {
                sh cmd
            }
        } else {
            sh cmd
        }
    }

    echo ""
    echo "✅ Spectra sync complete!"

    // Archive results if exported
    if (exportResults && fileExists(exportResults)) {
        archiveArtifacts artifacts: exportResults, allowEmptyArchive: true
    }
}

// Helper functions
def getTrackerEnvVars(String tracker, String jiraUrl) {
    def envVars = []

    switch (tracker) {
        case 'jira':
            if (jiraUrl) envVars.add("JIRA_URL=${jiraUrl}")
            break
        case 'github':
            if (env.GITHUB_OWNER) envVars.add("GITHUB_OWNER=${env.GITHUB_OWNER}")
            if (env.GITHUB_REPO) envVars.add("GITHUB_REPO=${env.GITHUB_REPO}")
            break
        case 'azure-devops':
            if (env.AZURE_ORGANIZATION) envVars.add("AZURE_ORGANIZATION=${env.AZURE_ORGANIZATION}")
            if (env.AZURE_PROJECT) envVars.add("AZURE_PROJECT=${env.AZURE_PROJECT}")
            break
        case 'linear':
            if (env.LINEAR_TEAM_ID) envVars.add("LINEAR_TEAM_ID=${env.LINEAR_TEAM_ID}")
            break
    }

    return envVars
}

def getCredentialsId(String tracker) {
    switch (tracker) {
        case 'jira':
            return 'jira-credentials'
        case 'github':
            return 'github-token'
        case 'azure-devops':
            return 'azure-devops-pat'
        case 'linear':
            return 'linear-api-key'
        default:
            return null
    }
}

def getCredentialUserVar(String tracker) {
    switch (tracker) {
        case 'jira':
            return 'JIRA_EMAIL'
        default:
            return 'API_USER'
    }
}

def getCredentialPassVar(String tracker) {
    switch (tracker) {
        case 'jira':
            return 'JIRA_API_TOKEN'
        case 'github':
            return 'GITHUB_TOKEN'
        case 'azure-devops':
            return 'AZURE_PAT'
        case 'linear':
            return 'LINEAR_API_KEY'
        default:
            return 'API_TOKEN'
    }
}
