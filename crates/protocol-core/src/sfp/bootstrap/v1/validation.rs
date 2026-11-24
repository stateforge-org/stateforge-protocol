//! Semantic validation for Bootstrap v1 messages.

use std::fmt;

use super::ProtocolVersion;

/// Bootstrap data violates the SFP semantic contract.
#[derive(Debug, PartialEq, Eq)]
pub enum BootstrapValidationError {
    /// A wire version has a zero major version.
    InvalidMajorVersion,
}

impl fmt::Display for BootstrapValidationError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidMajorVersion => {
                formatter.write_str("SFP major version must be a positive uint32")
            }
        }
    }
}

impl std::error::Error for BootstrapValidationError {}

/// Validate a wire version independently of runtime-supported versions.
///
/// # Errors
///
/// Returns [`BootstrapValidationError::InvalidMajorVersion`] when `major` is zero.
pub fn validate_protocol_version(
    version: &ProtocolVersion,
) -> Result<(), BootstrapValidationError> {
    if version.major == 0 {
        return Err(BootstrapValidationError::InvalidMajorVersion);
    }
    Ok(())
}
