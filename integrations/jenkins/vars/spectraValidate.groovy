// Spectra Jenkins Shared Library
// Validation function

def call(Map config = [:]) {
    def markdownFile = config.markdownFile
    if (!markdownFile) {
        error "markdownFile is required"
    }

    if (!fileExists(markdownFile)) {
        error "Markdown file not found: ${markdownFile}"
    }

    echo "✔️ Spectra Validation"
    echo "===================="

    sh """
        pip install --quiet spectra
        spectra validate --markdown ${markdownFile}
    """

    echo "✅ Validation passed!"
}
