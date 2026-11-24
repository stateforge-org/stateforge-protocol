use stateforge_protocol_core::sfp::bootstrap::v1::{
    ProtocolVersion,
    validation::{BootstrapValidationError, validate_protocol_version},
};

#[test]
fn accepts_wire_versions_within_the_sfp_range() {
    for (major, minor) in [(1, 0), (2, 7), (u32::MAX, u32::MAX)] {
        let version = ProtocolVersion { major, minor };
        assert_eq!(validate_protocol_version(&version), Ok(()));
    }
}

#[test]
fn rejects_zero_major_version() {
    let version = ProtocolVersion { major: 0, minor: 1 };
    assert_eq!(
        validate_protocol_version(&version),
        Err(BootstrapValidationError::InvalidMajorVersion)
    );
}

#[test]
fn rejects_default_wire_version() {
    assert_eq!(
        validate_protocol_version(&ProtocolVersion::default()),
        Err(BootstrapValidationError::InvalidMajorVersion)
    );
}
