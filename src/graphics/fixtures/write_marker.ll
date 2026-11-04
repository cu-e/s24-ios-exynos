; Project-owned synthetic AIR-shaped LLVM fixture. No Apple compiler or binary.
; One invocation writes an exactly representable integer into Metal buffer 0.
target triple = "air64-apple-ios16.5.0"

define void @write_marker(ptr addrspace(1) %out) {
entry:
  store i32 9212400, ptr addrspace(1) %out, align 4
  ret void
}

!air.kernel = !{!0}
!air.version = !{!5}
!0 = !{ptr @write_marker, !1, !2}
!1 = !{}
!2 = !{!3}
!3 = !{i32 0, !"air.buffer", !"air.location_index", i32 0, i32 1, !"air.read_write", !"air.address_space", i32 1, !"air.arg_type_size", i32 4, !"air.arg_type_align_size", i32 4, !"air.arg_type_name", !"uint", !"air.arg_name", !"out"}
!5 = !{i32 2, i32 4, i32 0}
