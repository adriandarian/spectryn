// Spectra Jenkins Shared Library
// Pull (reverse sync) function

def call(Map config = [:]) {
    def epicKey = config.epicKey
    def outputFile = config.outputFile
    def tracker = config.tracker ?: 'jira'
    def verbose = config.verbose ?: false

    if (!epicKey) {
        error "epicKey is required"
    }
    if (!outputFile) {
        error "outputFile is required"
    }

    echo "🔄 Spectra Pull (Reverse Sync)"
    echo "=============================="

    def cmd = "spectra pull --epic ${epicKey} --output ${outputFile} --tracker ${tracker}"

    if (verbose) {
        cmd += " --verbose"
    }

    sh """
        pip install --quiet spectra
        ${cmd}
    """

    echo "✅ Pull complete! Output: ${outputFile}"

    // Archive the output
    archiveArtifacts artifacts: outputFile, allowEmptyArchive: true
}
