//! Bootstrap v1 Python bindings.

use pyo3::exceptions::{PyTypeError, PyValueError};
use pyo3::prelude::*;
use stateforge_protocol_core::sfp::bootstrap::v1::{ProtocolVersion, validation};

/// Validate an existing Python protobuf ProtocolVersion through the Rust core.
#[pyfunction]
pub(crate) fn validate_protocol_version(version: &Bound<'_, PyAny>) -> PyResult<()> {
    let bootstrap = version
        .py()
        .import("stateforge_protocol.sfp.bootstrap.v1.bootstrap_pb2")?;
    if !version.is_instance(&bootstrap.getattr("ProtocolVersion")?)? {
        return Err(PyTypeError::new_err("version must be a ProtocolVersion"));
    }
    let wire_version = ProtocolVersion {
        major: version.getattr("major")?.extract()?,
        minor: version.getattr("minor")?.extract()?,
    };
    validation::validate_protocol_version(&wire_version)
        .map_err(|error| PyValueError::new_err(error.to_string()))
}
