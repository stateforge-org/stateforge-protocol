use pyo3::prelude::*;

mod sfp;

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(
        sfp::bootstrap::v1::validate_protocol_version,
        module
    )?)?;
    Ok(())
}
