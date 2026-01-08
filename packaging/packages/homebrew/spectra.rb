# frozen_string_literal: true

# Homebrew formula for spectra
# To install:
#   brew tap adriandarian/spectra https://github.com/adriandarian/spectra
#   brew install spectra
#
# Or install directly:
#   brew install adriandarian/spectra/spectra

class Spectra < Formula
  include Language::Python::Virtualenv

  desc "Production-grade CLI tool for synchronizing markdown documentation with Jira"
  homepage "https://github.com/adriandarian/spectra"
  url "https://github.com/adriandarian/spectra/archive/refs/tags/v2.0.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256_HASH"
  license "MIT"
  head "https://github.com/adriandarian/spectra.git", branch: "main"

  depends_on "python@3.12"

  resource "certifi" do
    url "https://files.pythonhosted.org/packages/certifi/certifi-2024.2.2.tar.gz"
    sha256 "PLACEHOLDER_CERTIFI_SHA256"
  end

  resource "charset-normalizer" do
    url "https://files.pythonhosted.org/packages/charset-normalizer/charset_normalizer-3.3.2.tar.gz"
    sha256 "PLACEHOLDER_CHARSET_SHA256"
  end

  resource "idna" do
    url "https://files.pythonhosted.org/packages/idna/idna-3.6.tar.gz"
    sha256 "PLACEHOLDER_IDNA_SHA256"
  end

  resource "pyyaml" do
    url "https://files.pythonhosted.org/packages/pyyaml/pyyaml-6.0.1.tar.gz"
    sha256 "PLACEHOLDER_PYYAML_SHA256"
  end

  resource "requests" do
    url "https://files.pythonhosted.org/packages/requests/requests-2.31.0.tar.gz"
    sha256 "PLACEHOLDER_REQUESTS_SHA256"
  end

  resource "urllib3" do
    url "https://files.pythonhosted.org/packages/urllib3/urllib3-2.2.1.tar.gz"
    sha256 "PLACEHOLDER_URLLIB3_SHA256"
  end

  def install
    virtualenv_install_with_resources

    # Generate shell completions
    generate_completions_from_executable(bin/"spectra", "--completions")
  end

  def caveats
    <<~EOS
      To use spectra, set these environment variables:
        export JIRA_URL="https://your-company.atlassian.net"
        export JIRA_EMAIL="your.email@company.com"
        export JIRA_API_TOKEN="your-api-token"

      Or create a config file at ~/.spectra.yaml

      Shell completions have been installed for bash, zsh, and fish.
    EOS
  end

  test do
    assert_match "spectra", shell_output("#{bin}/spectra --version")
    assert_match "usage:", shell_output("#{bin}/spectra --help")
  end
end

