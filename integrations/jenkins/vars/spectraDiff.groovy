// Spectra Jenkins Shared Library
// Diff function

def call(Map config = [:]) {
    def markdownFile = config.markdownFile
    def epicKey = config.epicKey
    def tracker = config.tracker ?: 'jira'

    if (!markdownFile) {
        error "markdownFile is required"
    }
    if (!epicKey) {
        error "epicKey is required"
    }

    echo "📊 Spectra Diff"
    echo "==============="

    sh """
        pip install --quiet spectra
        spectra diff --markdown ${markdownFile} --epic ${epicKey} --tracker ${tracker}
    """
}
