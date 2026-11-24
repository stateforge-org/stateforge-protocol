use std::path::PathBuf;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let repository_root = PathBuf::from(std::env::var("STATEFORGE_PROTOCOL_REPOSITORY_ROOT")?);
    let proto_root = repository_root.join("proto");
    let protoc = protoc_bin_vendored::protoc_bin_path()?;
    let protobuf_include = protoc_bin_vendored::include_path()?;

    let mut prost_config = tonic_prost_build::Config::new();
    prost_config.protoc_executable(protoc);
    let protos = [
        "stateforge_protocol/sfp/bootstrap/v1/bootstrap.proto",
        "stateforge_protocol/sfp/manifest/v1/manifest.proto",
        "stateforge_protocol/sfp/capability_assessment/v1/capability_assessment.proto",
        "stateforge_protocol/sfp/trigger_publication/v1/trigger_publication.proto",
        "stateforge_protocol/sfp/operation_admission/v1/operation_admission.proto",
        "stateforge_protocol/sfp/operation_lifecycle/v1/operation_lifecycle.proto",
    ];
    let proto_paths: Vec<_> = protos.iter().map(|path| proto_root.join(path)).collect();

    for proto in &proto_paths {
        println!("cargo:rerun-if-changed={}", proto.display());
    }
    println!("cargo:rerun-if-env-changed=STATEFORGE_PROTOCOL_REPOSITORY_ROOT");
    tonic_prost_build::configure()
        .build_client(true)
        .build_server(true)
        .compile_with_config(prost_config, &proto_paths, &[proto_root, protobuf_include])?;

    Ok(())
}
