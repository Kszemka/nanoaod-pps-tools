# AUTO GENERATED ON 2026-09-17 AT 19:00:59
# DO NOT EDIT BY HAND!
#
# To regenerate file, run
#
#     python dev/generate-kernel-signatures.py
#
# This step is normally run explicitly before generating a package

# fmt: off

# pylint: skip-file

from numpy import (
    bool_,
    int8,
    uint8,
    int16,
    uint16,
    int32,
    uint32,
    int64,
    uint64,
    float32,
    float64,
)

from awkward._connect.cuda import fetch_specialization
from awkward._connect.cuda import import_cupy

import math

cupy = import_cupy("Awkward Arrays with CUDA")

def by_signature(cuda_kernel_templates):
    out = {}

    def min_max_type(dtype):
      supported_types = {
          'bool': cupy.int32,
          'int8': cupy.int32,
          'int16': cupy.int32,
          'int32': cupy.int32,
          'int64': cupy.int64,
          'uint8': cupy.uint32,
          'uint16': cupy.uint32,
          'uint32': cupy.uint32,
          'uint64': cupy.uint64,
          'float32': cupy.float32,
          'float64': cupy.float64
      }
      if str(dtype) in supported_types:
          return supported_types[str(dtype)]
      else:
          raise ValueError("Unsupported dtype.", dtype)

    out['awkward_BitMaskedArray_to_ByteMaskedArray', int8, uint8] = None

    out['awkward_BitMaskedArray_to_IndexedOptionArray', int64, uint8] = None

    out['awkward_ByteMaskedArray_getitem_nextcarry', int64, int8] = None

    out['awkward_ByteMaskedArray_getitem_nextcarry_outindex', int64, int64, int8] = None

    out['awkward_ByteMaskedArray_numnull', int64, int8] = None

    out['awkward_ByteMaskedArray_overlay_mask', int8, int8, int8] = None

    out['awkward_ByteMaskedArray_reduce_next_64', int64, int64, int64, int8, int64] = None

    out['awkward_ByteMaskedArray_reduce_next_nonlocal_nextshifts_64', int64, int8] = None

    out['awkward_ByteMaskedArray_reduce_next_nonlocal_nextshifts_fromshifts_64', int64, int8, int64] = None

    out['awkward_ByteMaskedArray_toIndexedOptionArray', int64, int8] = None

    out['awkward_Content_getitem_next_missing_jagged_getmaskstartstop', int64, int64, int64, int64, int64] = None

    out['awkward_IndexedArray_fill', int64, int32] = None

    out['awkward_IndexedArray_fill', int64, int64] = None

    out['awkward_IndexedArray_fill', int64, uint32] = None

    out['awkward_IndexedArray_fill_count', int64] = None

    out['awkward_IndexedArray_flatten_nextcarry', int64, int32] = None

    out['awkward_IndexedArray_flatten_nextcarry', int64, int64] = None

    out['awkward_IndexedArray_flatten_nextcarry', int64, uint32] = None

    out['awkward_IndexedArray_flatten_none2empty', int64, int32, int64] = None

    out['awkward_IndexedArray_flatten_none2empty', int64, int64, int64] = None

    out['awkward_IndexedArray_flatten_none2empty', int64, uint32, int64] = None

    out['awkward_IndexedArray_getitem_nextcarry', int64, int32] = None

    out['awkward_IndexedArray_getitem_nextcarry', int64, int64] = None

    out['awkward_IndexedArray_getitem_nextcarry', int64, uint32] = None

    out['awkward_IndexedArray_getitem_nextcarry_outindex', int64, int32, int32] = None

    out['awkward_IndexedArray_getitem_nextcarry_outindex', int64, int64, int64] = None

    out['awkward_IndexedArray_getitem_nextcarry_outindex', int64, uint32, uint32] = None

    out['awkward_IndexedArray_local_preparenext_64', int64, int64, int64, int64] = None

    out['awkward_IndexedArray_numnull', int64, int32] = None

    out['awkward_IndexedArray_numnull', int64, int64] = None

    out['awkward_IndexedArray_numnull', int64, uint32] = None

    out['awkward_IndexedArray_numnull_parents', int64, int64, int32] = None

    out['awkward_IndexedArray_numnull_parents', int64, int64, int64] = None

    out['awkward_IndexedArray_numnull_parents', int64, int64, uint32] = None

    out['awkward_IndexedArray_numnull_unique_64', int64] = None

    out['awkward_IndexedArray_index_of_nulls', int64, int32, int64, int64] = None

    out['awkward_IndexedArray_index_of_nulls', int64, int64, int64, int64] = None

    out['awkward_IndexedArray_index_of_nulls', int64, uint32, int64, int64] = None

    out['awkward_IndexedArray_overlay_mask', int64, int8, int32] = None

    out['awkward_IndexedArray_overlay_mask', int64, int8, int64] = None

    out['awkward_IndexedArray_overlay_mask', int64, int8, uint32] = None

    out['awkward_IndexedArray_reduce_next_64', int64, int64, int64, int32, int64] = None

    out['awkward_IndexedArray_reduce_next_64', int64, int64, int64, int64, int64] = None

    out['awkward_IndexedArray_reduce_next_64', int64, int64, int64, uint32, int64] = None

    out['awkward_IndexedArray_reduce_next_fix_offsets_64', int64, int64] = None

    out['awkward_IndexedArray_unique_next_index_and_offsets_64', int64, int64, int64, int64] = None

    out['awkward_IndexedArray_reduce_next_nonlocal_nextshifts_64', int64, int32] = None

    out['awkward_IndexedArray_reduce_next_nonlocal_nextshifts_64', int64, int64] = None

    out['awkward_IndexedArray_reduce_next_nonlocal_nextshifts_64', int64, uint32] = None

    out['awkward_IndexedArray_reduce_next_nonlocal_nextshifts_fromshifts_64', int64, int32, int64] = None

    out['awkward_IndexedArray_reduce_next_nonlocal_nextshifts_fromshifts_64', int64, int64, int64] = None

    out['awkward_IndexedArray_reduce_next_nonlocal_nextshifts_fromshifts_64', int64, uint32, int64] = None

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_IndexedArray_simplify', int64, int32, int32]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True, False]
    out['awkward_IndexedArray_simplify', int64, int32, int32] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_IndexedArray_simplify', int64, int32, int64]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True, False]
    out['awkward_IndexedArray_simplify', int64, int32, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_IndexedArray_simplify', int64, int32, uint32]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True, False]
    out['awkward_IndexedArray_simplify', int64, int32, uint32] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_IndexedArray_simplify', int64, int64, int32]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True, False]
    out['awkward_IndexedArray_simplify', int64, int64, int32] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_IndexedArray_simplify', int64, int64, int64]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True, False]
    out['awkward_IndexedArray_simplify', int64, int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_IndexedArray_simplify', int64, int64, uint32]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True, False]
    out['awkward_IndexedArray_simplify', int64, int64, uint32] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_IndexedArray_simplify', int64, uint32, int32]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True, False]
    out['awkward_IndexedArray_simplify', int64, uint32, int32] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_IndexedArray_simplify', int64, uint32, int64]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True, False]
    out['awkward_IndexedArray_simplify', int64, uint32, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_IndexedArray_simplify', int64, uint32, uint32]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True, False]
    out['awkward_IndexedArray_simplify', int64, uint32, uint32] = f

    out['awkward_IndexedArray_validity', int32] = None

    out['awkward_IndexedArray_validity', int64] = None

    out['awkward_IndexedArray_validity', uint32] = None

    out['awkward_IndexedArray_ranges_next_64', int32, int64, int64, int64, int64, int64] = None

    out['awkward_IndexedArray_ranges_next_64', int64, int64, int64, int64, int64, int64] = None

    out['awkward_IndexedArray_ranges_next_64', uint32, int64, int64, int64, int64, int64] = None

    out['awkward_IndexedArray_ranges_carry_next_64', int32, int64, int64, int64] = None

    out['awkward_IndexedArray_ranges_carry_next_64', int64, int64, int64, int64] = None

    out['awkward_IndexedArray_ranges_carry_next_64', uint32, int64, int64, int64] = None

    out['awkward_IndexedOptionArray_rpad_and_clip_mask_axis1', int64, int8] = None

    out['awkward_ListArray_broadcast_tooffsets', int64, int64, int32, int32] = None

    out['awkward_ListArray_broadcast_tooffsets', int64, int64, int64, int64] = None

    out['awkward_ListArray_broadcast_tooffsets', int64, int64, uint32, uint32] = None

    out['awkward_ListArray_combinations', int64, int64, int64, int32, int32] = None

    out['awkward_ListArray_combinations', int64, int64, int64, int64, int64] = None

    out['awkward_ListArray_combinations', int64, int64, int64, uint32, uint32] = None

    out['awkward_ListArray_combinations_length', int64, int64, int32, int32] = None

    out['awkward_ListArray_combinations_length', int64, int64, int64, int64] = None

    out['awkward_ListArray_combinations_length', int64, int64, uint32, uint32] = None

    out['awkward_ListArray_compact_offsets', int64, int32, int32] = None

    out['awkward_ListArray_compact_offsets', int64, int64, int64] = None

    out['awkward_ListArray_compact_offsets', int64, uint32, uint32] = None

    out['awkward_ListArray_fill', int64, int64, int32, int32] = None

    out['awkward_ListArray_fill', int64, int64, int64, int64] = None

    out['awkward_ListArray_fill', int64, int64, uint32, uint32] = None

    def f(grid, block, args):
        (tooffsets, tocarry, slicestarts, slicestops, sliceouterlen, sliceindex, sliceinnerlen, fromstarts, fromstops, contentlen, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(sliceouterlen + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_jagged_apply_a", tooffsets.dtype, tocarry.dtype, slicestarts.dtype, slicestops.dtype, sliceindex.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, slicestarts, slicestops, sliceouterlen, sliceindex, sliceinnerlen, fromstarts, fromstops, contentlen, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_jagged_apply_b", tooffsets.dtype, tocarry.dtype, slicestarts.dtype, slicestops.dtype, sliceindex.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, slicestarts, slicestops, sliceouterlen, sliceindex, sliceinnerlen, fromstarts, fromstops, contentlen, scan_in_array, invocation_index, err_code))
    out["awkward_ListArray_getitem_jagged_apply_a", int64, int64, int64, int64, int64, int32, int32] = None
    out["awkward_ListArray_getitem_jagged_apply_b", int64, int64, int64, int64, int64, int32, int32] = None
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, False, True, False, True, True, False]
    out['awkward_ListArray_getitem_jagged_apply', int64, int64, int64, int64, int64, int32, int32] = f

    def f(grid, block, args):
        (tooffsets, tocarry, slicestarts, slicestops, sliceouterlen, sliceindex, sliceinnerlen, fromstarts, fromstops, contentlen, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(sliceouterlen + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_jagged_apply_a", tooffsets.dtype, tocarry.dtype, slicestarts.dtype, slicestops.dtype, sliceindex.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, slicestarts, slicestops, sliceouterlen, sliceindex, sliceinnerlen, fromstarts, fromstops, contentlen, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_jagged_apply_b", tooffsets.dtype, tocarry.dtype, slicestarts.dtype, slicestops.dtype, sliceindex.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, slicestarts, slicestops, sliceouterlen, sliceindex, sliceinnerlen, fromstarts, fromstops, contentlen, scan_in_array, invocation_index, err_code))
    out["awkward_ListArray_getitem_jagged_apply_a", int64, int64, int64, int64, int64, int64, int64] = None
    out["awkward_ListArray_getitem_jagged_apply_b", int64, int64, int64, int64, int64, int64, int64] = None
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, False, True, False, True, True, False]
    out['awkward_ListArray_getitem_jagged_apply', int64, int64, int64, int64, int64, int64, int64] = f

    def f(grid, block, args):
        (tooffsets, tocarry, slicestarts, slicestops, sliceouterlen, sliceindex, sliceinnerlen, fromstarts, fromstops, contentlen, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(sliceouterlen + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_jagged_apply_a", tooffsets.dtype, tocarry.dtype, slicestarts.dtype, slicestops.dtype, sliceindex.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, slicestarts, slicestops, sliceouterlen, sliceindex, sliceinnerlen, fromstarts, fromstops, contentlen, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_jagged_apply_b", tooffsets.dtype, tocarry.dtype, slicestarts.dtype, slicestops.dtype, sliceindex.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, slicestarts, slicestops, sliceouterlen, sliceindex, sliceinnerlen, fromstarts, fromstops, contentlen, scan_in_array, invocation_index, err_code))
    out["awkward_ListArray_getitem_jagged_apply_a", int64, int64, int64, int64, int64, uint32, uint32] = None
    out["awkward_ListArray_getitem_jagged_apply_b", int64, int64, int64, int64, int64, uint32, uint32] = None
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, False, True, False, True, True, False]
    out['awkward_ListArray_getitem_jagged_apply', int64, int64, int64, int64, int64, uint32, uint32] = f

    out['awkward_ListArray_getitem_jagged_carrylen', int64, int64, int64] = None

    out['awkward_ListArray_getitem_jagged_descend', int64, int64, int64, int32, int32] = None

    out['awkward_ListArray_getitem_jagged_descend', int64, int64, int64, int64, int64] = None

    out['awkward_ListArray_getitem_jagged_descend', int64, int64, int64, uint32, uint32] = None

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_jagged_expand', int64, int64, int64, int64, int32, int32]))(grid, block, args)
    f.dir = ['out', 'out', 'in', 'out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, True, False, False]
    out['awkward_ListArray_getitem_jagged_expand', int64, int64, int64, int64, int32, int32] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_jagged_expand', int64, int64, int64, int64, int64, int64]))(grid, block, args)
    f.dir = ['out', 'out', 'in', 'out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, True, False, False]
    out['awkward_ListArray_getitem_jagged_expand', int64, int64, int64, int64, int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_jagged_expand', int64, int64, int64, int64, uint32, uint32]))(grid, block, args)
    f.dir = ['out', 'out', 'in', 'out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, True, False, False]
    out['awkward_ListArray_getitem_jagged_expand', int64, int64, int64, int64, uint32, uint32] = f

    out['awkward_ListArray_getitem_jagged_numvalid', int64, int64, int64, int64] = None

    def f(grid, block, args):
        (tocarry, tosmalloffsets, tolargeoffsets, slicestarts, slicestops, length, missing, invocation_index, err_code) = args
        scan_in_array_k = cupy.zeros(length + 1, dtype=cupy.int64)
        scan_in_array_tosmalloffsets = cupy.zeros(length + 1, dtype=cupy.int64)
        scan_in_array_tolargeoffsets = cupy.zeros(length + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_jagged_shrink_a", tocarry.dtype, tosmalloffsets.dtype, tolargeoffsets.dtype, slicestarts.dtype, slicestops.dtype, missing.dtype]))(grid, block, (tocarry, tosmalloffsets, tolargeoffsets, slicestarts, slicestops, length, missing, scan_in_array_k, scan_in_array_tosmalloffsets, scan_in_array_tolargeoffsets, invocation_index, err_code))
        scan_in_array_k = cupy.cumsum(scan_in_array_k)
        scan_in_array_tosmalloffsets = cupy.cumsum(scan_in_array_tosmalloffsets)
        scan_in_array_tolargeoffsets = cupy.cumsum(scan_in_array_tolargeoffsets)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_jagged_shrink_b", tocarry.dtype, tosmalloffsets.dtype, tolargeoffsets.dtype, slicestarts.dtype, slicestops.dtype, missing.dtype]))(grid, block, (tocarry, tosmalloffsets, tolargeoffsets, slicestarts, slicestops, length, missing, scan_in_array_k, scan_in_array_tosmalloffsets, scan_in_array_tolargeoffsets, invocation_index, err_code))
    out["awkward_ListArray_getitem_jagged_shrink_a", int64, int64, int64, int64, int64, int64] = None
    out["awkward_ListArray_getitem_jagged_shrink_b", int64, int64, int64, int64, int64, int64] = None
    f.dir = ['out', 'out', 'out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, False, True]
    out['awkward_ListArray_getitem_jagged_shrink', int64, int64, int64, int64, int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_next_array', int64, int64, int32, int32, int64]))(grid, block, args)
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, False, False, False]
    out['awkward_ListArray_getitem_next_array', int64, int64, int32, int32, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_next_array', int64, int64, int64, int64, int64]))(grid, block, args)
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, False, False, False]
    out['awkward_ListArray_getitem_next_array', int64, int64, int64, int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_next_array', int64, int64, uint32, uint32, int64]))(grid, block, args)
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, False, False, False]
    out['awkward_ListArray_getitem_next_array', int64, int64, uint32, uint32, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_next_array_advanced', int64, int64, int32, int32, int64, int64]))(grid, block, args)
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, True, False, False]
    out['awkward_ListArray_getitem_next_array_advanced', int64, int64, int32, int32, int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_next_array_advanced', int64, int64, int64, int64, int64, int64]))(grid, block, args)
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, True, False, False]
    out['awkward_ListArray_getitem_next_array_advanced', int64, int64, int64, int64, int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_next_array_advanced', int64, int64, uint32, uint32, int64, int64]))(grid, block, args)
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, True, False, False]
    out['awkward_ListArray_getitem_next_array_advanced', int64, int64, uint32, uint32, int64, int64] = f

    def f(grid, block, args):
        (tocarry, fromstarts, fromstops, lenstarts, at, invocation_index, err_code) = args
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_next_at", tocarry.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tocarry, fromstarts, fromstops, lenstarts, cupy.array(at), invocation_index, err_code))
    out["awkward_ListArray_getitem_next_at", int64, int32, int32] = None
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, True]
    out['awkward_ListArray_getitem_next_at', int64, int32, int32] = f

    def f(grid, block, args):
        (tocarry, fromstarts, fromstops, lenstarts, at, invocation_index, err_code) = args
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_next_at", tocarry.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tocarry, fromstarts, fromstops, lenstarts, cupy.array(at), invocation_index, err_code))
    out["awkward_ListArray_getitem_next_at", int64, int64, int64] = None
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, True]
    out['awkward_ListArray_getitem_next_at', int64, int64, int64] = f

    def f(grid, block, args):
        (tocarry, fromstarts, fromstops, lenstarts, at, invocation_index, err_code) = args
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_next_at", tocarry.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tocarry, fromstarts, fromstops, lenstarts, cupy.array(at), invocation_index, err_code))
    out["awkward_ListArray_getitem_next_at", int64, uint32, uint32] = None
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, True]
    out['awkward_ListArray_getitem_next_at', int64, uint32, uint32] = f

    def f(grid, block, args):
        (tooffsets, tocarry, fromstarts, fromstops, lenstarts, start, stop, step, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(lenstarts + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_next_range_a", tooffsets.dtype, tocarry.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, fromstarts, fromstops, lenstarts, start, stop, step, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_next_range_b", tooffsets.dtype, tocarry.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, fromstarts, fromstops, lenstarts, start, stop, step, scan_in_array, invocation_index, err_code))
    out["awkward_ListArray_getitem_next_range_a", int32, int64, int32, int32] = None
    out["awkward_ListArray_getitem_next_range_b", int32, int64, int32, int32] = None
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, False, False, False, False]
    out['awkward_ListArray_getitem_next_range', int32, int64, int32, int32] = f

    def f(grid, block, args):
        (tooffsets, tocarry, fromstarts, fromstops, lenstarts, start, stop, step, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(lenstarts + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_next_range_a", tooffsets.dtype, tocarry.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, fromstarts, fromstops, lenstarts, start, stop, step, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_next_range_b", tooffsets.dtype, tocarry.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, fromstarts, fromstops, lenstarts, start, stop, step, scan_in_array, invocation_index, err_code))
    out["awkward_ListArray_getitem_next_range_a", int64, int64, int64, int64] = None
    out["awkward_ListArray_getitem_next_range_b", int64, int64, int64, int64] = None
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, False, False, False, False]
    out['awkward_ListArray_getitem_next_range', int64, int64, int64, int64] = f

    def f(grid, block, args):
        (tooffsets, tocarry, fromstarts, fromstops, lenstarts, start, stop, step, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(lenstarts + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_next_range_a", tooffsets.dtype, tocarry.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, fromstarts, fromstops, lenstarts, start, stop, step, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_getitem_next_range_b", tooffsets.dtype, tocarry.dtype, fromstarts.dtype, fromstops.dtype]))(grid, block, (tooffsets, tocarry, fromstarts, fromstops, lenstarts, start, stop, step, scan_in_array, invocation_index, err_code))
    out["awkward_ListArray_getitem_next_range_a", uint32, int64, uint32, uint32] = None
    out["awkward_ListArray_getitem_next_range_b", uint32, int64, uint32, uint32] = None
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, False, False, False, False]
    out['awkward_ListArray_getitem_next_range', uint32, int64, uint32, uint32] = f

    out['awkward_ListArray_getitem_next_range_carrylength', int64, int32, int32] = None

    out['awkward_ListArray_getitem_next_range_carrylength', int64, int64, int64] = None

    out['awkward_ListArray_getitem_next_range_carrylength', int64, uint32, uint32] = None

    out['awkward_ListArray_getitem_next_range_counts', int64, int32] = None

    out['awkward_ListArray_getitem_next_range_counts', int64, int64] = None

    out['awkward_ListArray_getitem_next_range_counts', int64, uint32] = None

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_next_range_spreadadvanced', int64, int64, int32]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False]
    out['awkward_ListArray_getitem_next_range_spreadadvanced', int64, int64, int32] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_next_range_spreadadvanced', int64, int64, int64]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False]
    out['awkward_ListArray_getitem_next_range_spreadadvanced', int64, int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_getitem_next_range_spreadadvanced', int64, int64, uint32]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False]
    out['awkward_ListArray_getitem_next_range_spreadadvanced', int64, int64, uint32] = f

    out['awkward_ListArray_localindex', int64, int32] = None

    out['awkward_ListArray_localindex', int64, int64] = None

    out['awkward_ListArray_localindex', int64, uint32] = None

    out['awkward_ListArray_min_range', int64, int32, int32] = None

    out['awkward_ListArray_min_range', int64, int64, int64] = None

    out['awkward_ListArray_min_range', int64, uint32, uint32] = None

    out['awkward_ListArray_rpad_and_clip_length_axis1', int64, int32, int32] = None

    out['awkward_ListArray_rpad_and_clip_length_axis1', int64, int64, int64] = None

    out['awkward_ListArray_rpad_and_clip_length_axis1', int64, uint32, uint32] = None

    def f(grid, block, args):
        (toindex, fromstarts, fromstops, tostarts, tostops, target, length, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(length, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_rpad_axis1_a", toindex.dtype, fromstarts.dtype, fromstops.dtype, tostarts.dtype, tostops.dtype]))(grid, block, (toindex, fromstarts, fromstops, tostarts, tostops, target, length, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_rpad_axis1_b", toindex.dtype, fromstarts.dtype, fromstops.dtype, tostarts.dtype, tostops.dtype]))(grid, block, (toindex, fromstarts, fromstops, tostarts, tostops, target, length, scan_in_array, invocation_index, err_code))
    out["awkward_ListArray_rpad_axis1_a", int64, int32, int32, int32, int32] = None
    out["awkward_ListArray_rpad_axis1_b", int64, int32, int32, int32, int32] = None
    f.dir = ['out', 'in', 'in', 'out', 'out', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, False, False]
    out['awkward_ListArray_rpad_axis1', int64, int32, int32, int32, int32] = f

    def f(grid, block, args):
        (toindex, fromstarts, fromstops, tostarts, tostops, target, length, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(length, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_rpad_axis1_a", toindex.dtype, fromstarts.dtype, fromstops.dtype, tostarts.dtype, tostops.dtype]))(grid, block, (toindex, fromstarts, fromstops, tostarts, tostops, target, length, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_rpad_axis1_b", toindex.dtype, fromstarts.dtype, fromstops.dtype, tostarts.dtype, tostops.dtype]))(grid, block, (toindex, fromstarts, fromstops, tostarts, tostops, target, length, scan_in_array, invocation_index, err_code))
    out["awkward_ListArray_rpad_axis1_a", int64, int64, int64, int64, int64] = None
    out["awkward_ListArray_rpad_axis1_b", int64, int64, int64, int64, int64] = None
    f.dir = ['out', 'in', 'in', 'out', 'out', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, False, False]
    out['awkward_ListArray_rpad_axis1', int64, int64, int64, int64, int64] = f

    def f(grid, block, args):
        (toindex, fromstarts, fromstops, tostarts, tostops, target, length, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(length, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_rpad_axis1_a", toindex.dtype, fromstarts.dtype, fromstops.dtype, tostarts.dtype, tostops.dtype]))(grid, block, (toindex, fromstarts, fromstops, tostarts, tostops, target, length, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListArray_rpad_axis1_b", toindex.dtype, fromstarts.dtype, fromstops.dtype, tostarts.dtype, tostops.dtype]))(grid, block, (toindex, fromstarts, fromstops, tostarts, tostops, target, length, scan_in_array, invocation_index, err_code))
    out["awkward_ListArray_rpad_axis1_a", int64, uint32, uint32, uint32, uint32] = None
    out["awkward_ListArray_rpad_axis1_b", int64, uint32, uint32, uint32, uint32] = None
    f.dir = ['out', 'in', 'in', 'out', 'out', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, False, False]
    out['awkward_ListArray_rpad_axis1', int64, uint32, uint32, uint32, uint32] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_validity', int32, int32]))(grid, block, args)
    f.dir = ['in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, False]
    out['awkward_ListArray_validity', int32, int32] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_validity', int64, int64]))(grid, block, args)
    f.dir = ['in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, False]
    out['awkward_ListArray_validity', int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListArray_validity', uint32, uint32]))(grid, block, args)
    f.dir = ['in', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, False]
    out['awkward_ListArray_validity', uint32, uint32] = f

    def f(grid, block, args):
        (tooffsets, noneindexes, fromoffsets, length_offsets, length_indexes, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(length_offsets, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_drop_none_indexes_a", tooffsets.dtype, noneindexes.dtype, fromoffsets.dtype]))(grid, block, (tooffsets, noneindexes, fromoffsets, length_offsets, length_indexes, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_drop_none_indexes_b", tooffsets.dtype, noneindexes.dtype, fromoffsets.dtype]))(grid, block, (tooffsets, noneindexes, fromoffsets, length_offsets, length_indexes, scan_in_array, invocation_index, err_code))
    out["awkward_ListOffsetArray_drop_none_indexes_a", int32, int32, int32] = None
    out["awkward_ListOffsetArray_drop_none_indexes_b", int32, int32, int32] = None
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, False]
    out['awkward_ListOffsetArray_drop_none_indexes', int32, int32, int32] = f

    def f(grid, block, args):
        (tooffsets, noneindexes, fromoffsets, length_offsets, length_indexes, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(length_offsets, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_drop_none_indexes_a", tooffsets.dtype, noneindexes.dtype, fromoffsets.dtype]))(grid, block, (tooffsets, noneindexes, fromoffsets, length_offsets, length_indexes, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_drop_none_indexes_b", tooffsets.dtype, noneindexes.dtype, fromoffsets.dtype]))(grid, block, (tooffsets, noneindexes, fromoffsets, length_offsets, length_indexes, scan_in_array, invocation_index, err_code))
    out["awkward_ListOffsetArray_drop_none_indexes_a", int64, int64, int64] = None
    out["awkward_ListOffsetArray_drop_none_indexes_b", int64, int64, int64] = None
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, False]
    out['awkward_ListOffsetArray_drop_none_indexes', int64, int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListOffsetArray_flatten_offsets', int64, int32, int64]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True]
    out['awkward_ListOffsetArray_flatten_offsets', int64, int32, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListOffsetArray_flatten_offsets', int64, int64, int64]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True]
    out['awkward_ListOffsetArray_flatten_offsets', int64, int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListOffsetArray_flatten_offsets', int64, uint32, int64]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, True]
    out['awkward_ListOffsetArray_flatten_offsets', int64, uint32, int64] = f

    out['awkward_ListOffsetArray_local_preparenext_64', int64, int64] = None

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListOffsetArray_reduce_local_nextparents_64', int32, int32]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, False]
    out['awkward_ListOffsetArray_reduce_local_nextparents_64', int32, int32] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListOffsetArray_reduce_local_nextparents_64', int64, int64]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, False]
    out['awkward_ListOffsetArray_reduce_local_nextparents_64', int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListOffsetArray_reduce_local_nextparents_64', uint32, uint32]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, False]
    out['awkward_ListOffsetArray_reduce_local_nextparents_64', uint32, uint32] = f

    out['awkward_ListOffsetArray_reduce_nonlocal_maxcount_offsetscopy_64', int64, int64, int64] = None

    out['awkward_ListOffsetArray_reduce_nonlocal_nextshifts_64', int64, int64, int64, int64, int64, int64, int64] = None

    def f(grid, block, args):
        (outstarts, outstops, distincts, lendistincts, outlength, invocation_index, err_code) = args
        if block[0] > 0:
            grid_size = math.floor((lendistincts + block[0] - 1) / block[0])
        else:
            grid_size = 1
        temp = cupy.zeros(lendistincts, dtype=cupy.int64)
        scan_in_array = cupy.zeros(outlength, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_reduce_nonlocal_outstartsstops_64_a", outstarts.dtype, outstops.dtype, distincts.dtype]))((grid_size,), block, (outstarts, outstops, distincts, lendistincts, outlength, temp, scan_in_array, invocation_index, err_code))
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_reduce_nonlocal_outstartsstops_64_b", outstarts.dtype, outstops.dtype, distincts.dtype]))((grid_size,), block, (outstarts, outstops, distincts, lendistincts, outlength, temp, scan_in_array, invocation_index, err_code))
    out["awkward_ListOffsetArray_reduce_nonlocal_outstartsstops_64_a", int64, int64, int64] = None
    out["awkward_ListOffsetArray_reduce_nonlocal_outstartsstops_64_b", int64, int64, int64] = None
    f.dir = ['out', 'out', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, False]
    out['awkward_ListOffsetArray_reduce_nonlocal_outstartsstops_64', int64, int64, int64] = f

    out['awkward_ListOffsetArray_reduce_nonlocal_preparenext_64', int64, int64, int64, int64, int64, int64, int64] = None

    out['awkward_ListOffsetArray_rpad_and_clip_axis1', int64, int32] = None

    out['awkward_ListOffsetArray_rpad_and_clip_axis1', int64, int64] = None

    out['awkward_ListOffsetArray_rpad_and_clip_axis1', int64, uint32] = None

    def f(grid, block, args):
        (toindex, fromoffsets, fromlength, target, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(fromlength + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_rpad_axis1_a", toindex.dtype, fromoffsets.dtype]))(grid, block, (toindex, fromoffsets, fromlength, target, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_rpad_axis1_b", toindex.dtype, fromoffsets.dtype]))(grid, block, (toindex, fromoffsets, fromlength, target, scan_in_array, invocation_index, err_code))
    out["awkward_ListOffsetArray_rpad_axis1_a", int64, int32] = None
    out["awkward_ListOffsetArray_rpad_axis1_b", int64, int32] = None
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, False]
    out['awkward_ListOffsetArray_rpad_axis1', int64, int32] = f

    def f(grid, block, args):
        (toindex, fromoffsets, fromlength, target, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(fromlength + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_rpad_axis1_a", toindex.dtype, fromoffsets.dtype]))(grid, block, (toindex, fromoffsets, fromlength, target, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_rpad_axis1_b", toindex.dtype, fromoffsets.dtype]))(grid, block, (toindex, fromoffsets, fromlength, target, scan_in_array, invocation_index, err_code))
    out["awkward_ListOffsetArray_rpad_axis1_a", int64, int64] = None
    out["awkward_ListOffsetArray_rpad_axis1_b", int64, int64] = None
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, False]
    out['awkward_ListOffsetArray_rpad_axis1', int64, int64] = f

    def f(grid, block, args):
        (toindex, fromoffsets, fromlength, target, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(fromlength + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_rpad_axis1_a", toindex.dtype, fromoffsets.dtype]))(grid, block, (toindex, fromoffsets, fromlength, target, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_ListOffsetArray_rpad_axis1_b", toindex.dtype, fromoffsets.dtype]))(grid, block, (toindex, fromoffsets, fromlength, target, scan_in_array, invocation_index, err_code))
    out["awkward_ListOffsetArray_rpad_axis1_a", int64, uint32] = None
    out["awkward_ListOffsetArray_rpad_axis1_b", int64, uint32] = None
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, False]
    out['awkward_ListOffsetArray_rpad_axis1', int64, uint32] = f

    out['awkward_ListOffsetArray_rpad_length_axis1', int32, int32, int64] = None

    out['awkward_ListOffsetArray_rpad_length_axis1', int64, int64, int64] = None

    out['awkward_ListOffsetArray_rpad_length_axis1', uint32, uint32, int64] = None

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListOffsetArray_toRegularArray', int64, int32]))(grid, block, args)
    f.dir = ['out', 'in', 'in']
    f.is_ptr = [True, True, False]
    out['awkward_ListOffsetArray_toRegularArray', int64, int32] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListOffsetArray_toRegularArray', int64, int64]))(grid, block, args)
    f.dir = ['out', 'in', 'in']
    f.is_ptr = [True, True, False]
    out['awkward_ListOffsetArray_toRegularArray', int64, int64] = f

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_ListOffsetArray_toRegularArray', int64, uint32]))(grid, block, args)
    f.dir = ['out', 'in', 'in']
    f.is_ptr = [True, True, False]
    out['awkward_ListOffsetArray_toRegularArray', int64, uint32] = f

    out['awkward_MaskedArray_getitem_next_jagged_project', int32, int64, int64, int64, int64] = None

    out['awkward_MaskedArray_getitem_next_jagged_project', int64, int64, int64, int64, int64] = None

    out['awkward_MaskedArray_getitem_next_jagged_project', uint32, int64, int64, int64, int64] = None

    out['awkward_NumpyArray_rearrange_shifted', int64, int64, int64, int64, int64] = None

    out['awkward_NumpyArray_reduce_adjust_starts_64', int64, int64, int64] = None

    out['awkward_NumpyArray_reduce_adjust_starts_shifts_64', int64, int64, int64, int64] = None

    out['awkward_NumpyArray_reduce_mask_ByteMaskedArray_64', int8, int64] = None

    out['awkward_ListOffsetArray_argsort_strings', int64, int64, uint8, int64, int64] = None

    out['awkward_NumpyArray_sort_asstrings_uint8', uint8, uint8, int64, int64] = None

    out['awkward_NumpyArray_unique_strings', uint8, int64, int64, int64] = None

    out['awkward_NumpyArray_prepare_utf8_to_utf32_padded', uint8, int32, int64] = None

    out['awkward_NumpyArray_prepare_utf8_to_utf32_padded', uint8, int64, int64] = None

    out['awkward_NumpyArray_prepare_utf8_to_utf32_padded', uint8, uint32, int64] = None

    out['awkward_NumpyArray_utf8_to_utf32_padded', uint8, int32, uint32] = None

    out['awkward_NumpyArray_utf8_to_utf32_padded', uint8, int64, uint32] = None

    out['awkward_NumpyArray_utf8_to_utf32_padded', uint8, uint32, uint32] = None

    out['awkward_NumpyArray_pad_zero_to_length', uint8, int32, uint8] = None

    out['awkward_NumpyArray_pad_zero_to_length', uint8, int64, uint8] = None

    out['awkward_NumpyArray_pad_zero_to_length', uint8, uint32, uint8] = None

    out['awkward_NumpyArray_subrange_equal_bool', bool_, int64, int64, bool_] = None

    out['awkward_NumpyArray_subrange_equal', int8, int64, int64, bool_] = None

    out['awkward_NumpyArray_subrange_equal', int16, int64, int64, bool_] = None

    out['awkward_NumpyArray_subrange_equal', int32, int64, int64, bool_] = None

    out['awkward_NumpyArray_subrange_equal', int64, int64, int64, bool_] = None

    out['awkward_NumpyArray_subrange_equal', uint8, int64, int64, bool_] = None

    out['awkward_NumpyArray_subrange_equal', uint16, int64, int64, bool_] = None

    out['awkward_NumpyArray_subrange_equal', uint32, int64, int64, bool_] = None

    out['awkward_NumpyArray_subrange_equal', uint64, int64, int64, bool_] = None

    out['awkward_NumpyArray_subrange_equal', float32, int64, int64, bool_] = None

    out['awkward_NumpyArray_subrange_equal', float64, int64, int64, bool_] = None

    def f(grid, block, args):
        (tocarry, toindex, fromindex, n, replacement, size, length, invocation_index, err_code) = args
        scan_in_array_offsets = cupy.zeros(length + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_RegularArray_combinations_64_a", tocarry[0].dtype, toindex.dtype, fromindex.dtype]))(grid, block, (tocarry, toindex, fromindex, n, replacement, size, length, scan_in_array_offsets, invocation_index, err_code))
        scan_in_array_offsets = cupy.cumsum(scan_in_array_offsets)
        # Compute total outputs and allocate local_indices
        total = int(scan_in_array_offsets[length])
        scan_in_array_local_indices = cupy.zeros(total, dtype=cupy.int64)
        # Compute parents as a run-length expansion of [0..length-1]
        # using cp.searchsorted
        if total > 0:
            scan_in_array_parents = cupy.searchsorted(scan_in_array_offsets[1:], cupy.arange(total), side='right').astype(cupy.int64)
        else:
            scan_in_array_parents = cupy.zeros(0, dtype=cupy.int64)
        if int(scan_in_array_offsets[length]) < 1024:
            block_size = int(scan_in_array_offsets[length])
        else:
            block_size = 1024
        if block_size > 0:
            grid_size = math.floor((int(scan_in_array_offsets[length]) + block_size - 1) / block_size)
        else:
            grid_size = 1
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_RegularArray_combinations_64_b", tocarry[0].dtype, toindex.dtype, fromindex.dtype]))((grid_size,), (block_size,), (tocarry, toindex, fromindex, n, replacement, size, length, scan_in_array_offsets, scan_in_array_parents, scan_in_array_local_indices, invocation_index, err_code))
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_RegularArray_combinations_64_c", tocarry[0].dtype, toindex.dtype, fromindex.dtype]))((grid_size,), (block_size,), (tocarry, toindex, fromindex, n, replacement, size, length, scan_in_array_offsets, scan_in_array_parents, scan_in_array_local_indices, invocation_index, err_code))
    out["awkward_RegularArray_combinations_64_a", int64, int64, int64] = None
    out["awkward_RegularArray_combinations_64_b", int64, int64, int64] = None
    out["awkward_RegularArray_combinations_64_c", int64, int64, int64] = None
    f.dir = ['out', 'out', 'in', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, False, False, False]
    out['awkward_RegularArray_combinations_64', int64, int64, int64] = f

    out['awkward_RegularArray_getitem_carry', int64, int64] = None

    out['awkward_RegularArray_getitem_jagged_expand', int64, int64, int64] = None

    out['awkward_RegularArray_getitem_next_array', int64, int64, int64] = None

    out['awkward_RegularArray_getitem_next_array_advanced', int64, int64, int64, int64] = None

    def f(grid, block, args):
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_RegularArray_getitem_next_array_regularize', int64, int64]))(grid, block, args)
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, True, False, False]
    out['awkward_RegularArray_getitem_next_array_regularize', int64, int64] = f

    out['awkward_RegularArray_getitem_next_at', int64] = None

    out['awkward_RegularArray_getitem_next_range', int64] = None

    out['awkward_RegularArray_getitem_next_range_spreadadvanced', int64, int64] = None

    out['awkward_RegularArray_localindex', int64] = None

    def f(grid, block, args):
        (nextparents, size, length, invocation_index, err_code) = args
        scan_in_array = cupy.ones(length * size, dtype=cupy.int64)
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_RegularArray_reduce_local_nextparents_64', nextparents.dtype]))(grid, block, (nextparents, size, length, scan_in_array, invocation_index, err_code))
    out["awkward_RegularArray_reduce_local_nextparents_64", int64] = None
    f.dir = ['out', 'in', 'in']
    f.is_ptr = [True, False, False]
    out['awkward_RegularArray_reduce_local_nextparents_64', int64] = f

    out['awkward_RegularArray_reduce_nonlocal_preparenext_64', int64, int64, int64] = None

    out['awkward_RegularArray_rpad_and_clip_axis1', int64] = None

    out['awkward_UnionArray_fillindex', int64, int32] = None

    out['awkward_UnionArray_fillindex', int64, int64] = None

    out['awkward_UnionArray_fillindex', int64, uint32] = None

    out['awkward_UnionArray_fillindex_count', int64] = None

    out['awkward_UnionArray_fillna', int64, int32] = None

    out['awkward_UnionArray_fillna', int64, int64] = None

    out['awkward_UnionArray_fillna', int64, uint32] = None

    out['awkward_UnionArray_filltags', int8, int8] = None

    out['awkward_UnionArray_filltags_const', int8] = None

    def f(grid, block, args):
        (totags, toindex, tooffsets, fromtags, fromindex, length, offsetsraws, invocation_index, err_code) = args
        scan_in_array_tooffsets = cupy.zeros(length + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_combine_a', totags.dtype, toindex.dtype, tooffsets.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (totags, toindex, tooffsets, fromtags, fromindex, length, offsetsraws, scan_in_array_tooffsets, invocation_index, err_code))
        scan_in_array_tooffsets = cupy.cumsum(scan_in_array_tooffsets)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_combine_b', totags.dtype, toindex.dtype, tooffsets.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (totags, toindex, tooffsets, fromtags, fromindex, length, offsetsraws, scan_in_array_tooffsets, invocation_index, err_code))
    out["awkward_UnionArray_flatten_combine_a", int8, int64, int64, int8, int32, int64] = None
    out["awkward_UnionArray_flatten_combine_b", int8, int64, int64, int8, int32, int64] = None
    f.dir = ['out', 'out', 'out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, False, True]
    out['awkward_UnionArray_flatten_combine', int8, int64, int64, int8, int32, int64] = f

    def f(grid, block, args):
        (totags, toindex, tooffsets, fromtags, fromindex, length, offsetsraws, invocation_index, err_code) = args
        scan_in_array_tooffsets = cupy.zeros(length + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_combine_a', totags.dtype, toindex.dtype, tooffsets.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (totags, toindex, tooffsets, fromtags, fromindex, length, offsetsraws, scan_in_array_tooffsets, invocation_index, err_code))
        scan_in_array_tooffsets = cupy.cumsum(scan_in_array_tooffsets)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_combine_b', totags.dtype, toindex.dtype, tooffsets.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (totags, toindex, tooffsets, fromtags, fromindex, length, offsetsraws, scan_in_array_tooffsets, invocation_index, err_code))
    out["awkward_UnionArray_flatten_combine_a", int8, int64, int64, int8, int64, int64] = None
    out["awkward_UnionArray_flatten_combine_b", int8, int64, int64, int8, int64, int64] = None
    f.dir = ['out', 'out', 'out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, False, True]
    out['awkward_UnionArray_flatten_combine', int8, int64, int64, int8, int64, int64] = f

    def f(grid, block, args):
        (totags, toindex, tooffsets, fromtags, fromindex, length, offsetsraws, invocation_index, err_code) = args
        scan_in_array_tooffsets = cupy.zeros(length + 1, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_combine_a', totags.dtype, toindex.dtype, tooffsets.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (totags, toindex, tooffsets, fromtags, fromindex, length, offsetsraws, scan_in_array_tooffsets, invocation_index, err_code))
        scan_in_array_tooffsets = cupy.cumsum(scan_in_array_tooffsets)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_combine_b', totags.dtype, toindex.dtype, tooffsets.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (totags, toindex, tooffsets, fromtags, fromindex, length, offsetsraws, scan_in_array_tooffsets, invocation_index, err_code))
    out["awkward_UnionArray_flatten_combine_a", int8, int64, int64, int8, uint32, int64] = None
    out["awkward_UnionArray_flatten_combine_b", int8, int64, int64, int8, uint32, int64] = None
    f.dir = ['out', 'out', 'out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, True, True, False, True]
    out['awkward_UnionArray_flatten_combine', int8, int64, int64, int8, uint32, int64] = f

    def f(grid, block, args):
        (total_length, fromtags, fromindex, length, offsetsraws, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(length, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_length_a', total_length.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (total_length, fromtags, fromindex, length, offsetsraws, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_length_b', total_length.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (total_length, fromtags, fromindex, length, offsetsraws, scan_in_array, invocation_index, err_code))
    out["awkward_UnionArray_flatten_length_a", int64, int8, int32, int64] = None
    out["awkward_UnionArray_flatten_length_b", int64, int8, int32, int64] = None
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, True]
    out['awkward_UnionArray_flatten_length', int64, int8, int32, int64] = f

    def f(grid, block, args):
        (total_length, fromtags, fromindex, length, offsetsraws, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(length, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_length_a', total_length.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (total_length, fromtags, fromindex, length, offsetsraws, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_length_b', total_length.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (total_length, fromtags, fromindex, length, offsetsraws, scan_in_array, invocation_index, err_code))
    out["awkward_UnionArray_flatten_length_a", int64, int8, int64, int64] = None
    out["awkward_UnionArray_flatten_length_b", int64, int8, int64, int64] = None
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, True]
    out['awkward_UnionArray_flatten_length', int64, int8, int64, int64] = f

    def f(grid, block, args):
        (total_length, fromtags, fromindex, length, offsetsraws, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(length, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_length_a', total_length.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (total_length, fromtags, fromindex, length, offsetsraws, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_UnionArray_flatten_length_b', total_length.dtype, fromtags.dtype, fromindex.dtype, offsetsraws[0].dtype]))(grid, block, (total_length, fromtags, fromindex, length, offsetsraws, scan_in_array, invocation_index, err_code))
    out["awkward_UnionArray_flatten_length_a", int64, int8, uint32, int64] = None
    out["awkward_UnionArray_flatten_length_b", int64, int8, uint32, int64] = None
    f.dir = ['out', 'in', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, True]
    out['awkward_UnionArray_flatten_length', int64, int8, uint32, int64] = f

    def f(grid, block, args):
        (totags, toindex, tmpstarts, tag, fromcounts, length, invocation_index, err_code) = args
        if length > 0:
            scan_in_array = cupy.zeros(int(tmpstarts[length -1] + fromcounts[length - 1]), dtype=cupy.int64)
        else:
            scan_in_array = cupy.zeros(length, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_UnionArray_nestedfill_tags_index_a", totags.dtype, toindex.dtype, tmpstarts.dtype, fromcounts.dtype]))(grid, block, (totags, toindex, tmpstarts, tag, fromcounts, length, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_UnionArray_nestedfill_tags_index_b", totags.dtype, toindex.dtype, tmpstarts.dtype, fromcounts.dtype]))(grid, block, (totags, toindex, tmpstarts, tag, fromcounts, length, scan_in_array, invocation_index, err_code))
    out["awkward_UnionArray_nestedfill_tags_index_a", int64, int64, int64, int64] = None
    out["awkward_UnionArray_nestedfill_tags_index_b", int64, int64, int64, int64] = None
    f.dir = ['out', 'out', 'out', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, True, False]
    out['awkward_UnionArray_nestedfill_tags_index', int64, int64, int64, int64] = f

    def f(grid, block, args):
        (totags, toindex, tmpstarts, tag, fromcounts, length, invocation_index, err_code) = args
        if length > 0:
            scan_in_array = cupy.zeros(int(tmpstarts[length -1] + fromcounts[length - 1]), dtype=cupy.int64)
        else:
            scan_in_array = cupy.zeros(length, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_UnionArray_nestedfill_tags_index_a", totags.dtype, toindex.dtype, tmpstarts.dtype, fromcounts.dtype]))(grid, block, (totags, toindex, tmpstarts, tag, fromcounts, length, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_UnionArray_nestedfill_tags_index_b", totags.dtype, toindex.dtype, tmpstarts.dtype, fromcounts.dtype]))(grid, block, (totags, toindex, tmpstarts, tag, fromcounts, length, scan_in_array, invocation_index, err_code))
    out["awkward_UnionArray_nestedfill_tags_index_a", int8, int32, int64, int64] = None
    out["awkward_UnionArray_nestedfill_tags_index_b", int8, int32, int64, int64] = None
    f.dir = ['out', 'out', 'out', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, True, False]
    out['awkward_UnionArray_nestedfill_tags_index', int8, int32, int64, int64] = f

    def f(grid, block, args):
        (totags, toindex, tmpstarts, tag, fromcounts, length, invocation_index, err_code) = args
        if length > 0:
            scan_in_array = cupy.zeros(int(tmpstarts[length -1] + fromcounts[length - 1]), dtype=cupy.int64)
        else:
            scan_in_array = cupy.zeros(length, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_UnionArray_nestedfill_tags_index_a", totags.dtype, toindex.dtype, tmpstarts.dtype, fromcounts.dtype]))(grid, block, (totags, toindex, tmpstarts, tag, fromcounts, length, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_UnionArray_nestedfill_tags_index_b", totags.dtype, toindex.dtype, tmpstarts.dtype, fromcounts.dtype]))(grid, block, (totags, toindex, tmpstarts, tag, fromcounts, length, scan_in_array, invocation_index, err_code))
    out["awkward_UnionArray_nestedfill_tags_index_a", int8, int64, int64, int64] = None
    out["awkward_UnionArray_nestedfill_tags_index_b", int8, int64, int64, int64] = None
    f.dir = ['out', 'out', 'out', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, True, False]
    out['awkward_UnionArray_nestedfill_tags_index', int8, int64, int64, int64] = f

    def f(grid, block, args):
        (totags, toindex, tmpstarts, tag, fromcounts, length, invocation_index, err_code) = args
        if length > 0:
            scan_in_array = cupy.zeros(int(tmpstarts[length -1] + fromcounts[length - 1]), dtype=cupy.int64)
        else:
            scan_in_array = cupy.zeros(length, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_UnionArray_nestedfill_tags_index_a", totags.dtype, toindex.dtype, tmpstarts.dtype, fromcounts.dtype]))(grid, block, (totags, toindex, tmpstarts, tag, fromcounts, length, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(["awkward_UnionArray_nestedfill_tags_index_b", totags.dtype, toindex.dtype, tmpstarts.dtype, fromcounts.dtype]))(grid, block, (totags, toindex, tmpstarts, tag, fromcounts, length, scan_in_array, invocation_index, err_code))
    out["awkward_UnionArray_nestedfill_tags_index_a", int8, uint32, int64, int64] = None
    out["awkward_UnionArray_nestedfill_tags_index_b", int8, uint32, int64, int64] = None
    f.dir = ['out', 'out', 'out', 'in', 'in', 'in']
    f.is_ptr = [True, True, True, False, True, False]
    out['awkward_UnionArray_nestedfill_tags_index', int8, uint32, int64, int64] = f

    out['awkward_UnionArray_project', int64, int64, int8, int32] = None

    out['awkward_UnionArray_project', int64, int64, int8, int64] = None

    out['awkward_UnionArray_project', int64, int64, int8, uint32] = None

    out['awkward_UnionArray_regular_index', int32, int32, int64] = None

    out['awkward_UnionArray_regular_index', int64, int64, int64] = None

    out['awkward_UnionArray_regular_index', uint32, uint32, int64] = None

    out['awkward_UnionArray_regular_index', int32, int32, int8] = None

    out['awkward_UnionArray_regular_index', int64, int64, int8] = None

    out['awkward_UnionArray_regular_index', uint32, uint32, int8] = None

    out['awkward_UnionArray_regular_index_getsize', int64, int64] = None

    out['awkward_UnionArray_regular_index_getsize', int64, int8] = None

    out['awkward_UnionArray_simplify', int8, int64, int64, int64, int8, int64] = None

    out['awkward_UnionArray_simplify', int8, int64, int8, int32, int8, int32] = None

    out['awkward_UnionArray_simplify', int8, int64, int8, int32, int8, int64] = None

    out['awkward_UnionArray_simplify', int8, int64, int8, int32, int8, uint32] = None

    out['awkward_UnionArray_simplify', int8, int64, int8, int64, int8, int32] = None

    out['awkward_UnionArray_simplify', int8, int64, int8, int64, int8, int64] = None

    out['awkward_UnionArray_simplify', int8, int64, int8, int64, int8, uint32] = None

    out['awkward_UnionArray_simplify', int8, int64, int8, uint32, int8, int32] = None

    out['awkward_UnionArray_simplify', int8, int64, int8, uint32, int8, int64] = None

    out['awkward_UnionArray_simplify', int8, int64, int8, uint32, int8, uint32] = None

    out['awkward_UnionArray_simplify_one', int8, int64, int64, int64] = None

    out['awkward_UnionArray_simplify_one', int8, int64, int8, int32] = None

    out['awkward_UnionArray_simplify_one', int8, int64, int8, int64] = None

    out['awkward_UnionArray_simplify_one', int8, int64, int8, uint32] = None

    out['awkward_UnionArray_validity', int8, int32, int64] = None

    out['awkward_UnionArray_validity', int8, int64, int64] = None

    out['awkward_UnionArray_validity', int8, uint32, int64] = None

    out['awkward_argsort', int64, bool_, int32] = None

    out['awkward_argsort', int64, bool_, uint32] = None

    out['awkward_argsort', int64, bool_, uint64] = None

    out['awkward_argsort', int64, bool_, int64] = None

    out['awkward_argsort', int64, int8, int32] = None

    out['awkward_argsort', int64, int8, uint32] = None

    out['awkward_argsort', int64, int8, uint64] = None

    out['awkward_argsort', int64, int8, int64] = None

    out['awkward_argsort', int64, int16, int32] = None

    out['awkward_argsort', int64, int16, uint32] = None

    out['awkward_argsort', int64, int16, uint64] = None

    out['awkward_argsort', int64, int16, int64] = None

    out['awkward_argsort', int64, int32, int32] = None

    out['awkward_argsort', int64, int32, uint32] = None

    out['awkward_argsort', int64, int32, uint64] = None

    out['awkward_argsort', int64, int32, int64] = None

    out['awkward_argsort', int64, int64, int32] = None

    out['awkward_argsort', int64, int64, uint32] = None

    out['awkward_argsort', int64, int64, uint64] = None

    out['awkward_argsort', int64, int64, int64] = None

    out['awkward_argsort', int64, uint8, int32] = None

    out['awkward_argsort', int64, uint8, uint32] = None

    out['awkward_argsort', int64, uint8, uint64] = None

    out['awkward_argsort', int64, uint8, int64] = None

    out['awkward_argsort', int64, uint16, int32] = None

    out['awkward_argsort', int64, uint16, uint32] = None

    out['awkward_argsort', int64, uint16, uint64] = None

    out['awkward_argsort', int64, uint16, int64] = None

    out['awkward_argsort', int64, uint32, int32] = None

    out['awkward_argsort', int64, uint32, uint32] = None

    out['awkward_argsort', int64, uint32, uint64] = None

    out['awkward_argsort', int64, uint32, int64] = None

    out['awkward_argsort', int64, uint64, int32] = None

    out['awkward_argsort', int64, uint64, uint32] = None

    out['awkward_argsort', int64, uint64, uint64] = None

    out['awkward_argsort', int64, uint64, int64] = None

    out['awkward_argsort', int64, float32, int32] = None

    out['awkward_argsort', int64, float32, uint32] = None

    out['awkward_argsort', int64, float32, uint64] = None

    out['awkward_argsort', int64, float32, int64] = None

    out['awkward_argsort', int64, float64, int32] = None

    out['awkward_argsort', int64, float64, uint32] = None

    out['awkward_argsort', int64, float64, uint64] = None

    out['awkward_argsort', int64, float64, int64] = None

    out['awkward_index_rpad_and_clip_axis0', int64] = None

    out['awkward_index_rpad_and_clip_axis1', int64, int64] = None

    out['awkward_Index_nones_as_index', int64] = None

    out['awkward_localindex', int64] = None

    out['awkward_missing_repeat', int64, int64] = None

    out['awkward_reduce_argmax', int64, int8, int64, int64] = None

    out['awkward_reduce_argmax', int64, uint8, int64, int64] = None

    out['awkward_reduce_argmax', int64, int16, int64, int64] = None

    out['awkward_reduce_argmax', int64, uint16, int64, int64] = None

    out['awkward_reduce_argmax', int64, int32, int64, int64] = None

    out['awkward_reduce_argmax', int64, uint32, int64, int64] = None

    out['awkward_reduce_argmax', int64, int64, int64, int64] = None

    out['awkward_reduce_argmax', int64, uint64, int64, int64] = None

    out['awkward_reduce_argmax', int64, float32, int64, int64] = None

    out['awkward_reduce_argmax', int64, float64, int64, int64] = None

    out['awkward_reduce_argmax_complex', int64, float32, int64] = None

    out['awkward_reduce_argmax_complex', int64, float64, int64] = None

    out['awkward_reduce_argmin', int64, int8, int64, int64] = None

    out['awkward_reduce_argmin', int64, uint8, int64, int64] = None

    out['awkward_reduce_argmin', int64, int16, int64, int64] = None

    out['awkward_reduce_argmin', int64, uint16, int64, int64] = None

    out['awkward_reduce_argmin', int64, int32, int64, int64] = None

    out['awkward_reduce_argmin', int64, uint32, int64, int64] = None

    out['awkward_reduce_argmin', int64, int64, int64, int64] = None

    out['awkward_reduce_argmin', int64, uint64, int64, int64] = None

    out['awkward_reduce_argmin', int64, float32, int64, int64] = None

    out['awkward_reduce_argmin', int64, float64, int64, int64] = None

    out['awkward_reduce_argmin_complex', int64, float32, int64] = None

    out['awkward_reduce_argmin_complex', int64, float64, int64] = None

    out['awkward_reduce_count_64', int64, int64] = None

    out['awkward_reduce_countnonzero', int64, bool_, int64] = None

    out['awkward_reduce_countnonzero', int64, int8, int64] = None

    out['awkward_reduce_countnonzero', int64, uint8, int64] = None

    out['awkward_reduce_countnonzero', int64, int16, int64] = None

    out['awkward_reduce_countnonzero', int64, uint16, int64] = None

    out['awkward_reduce_countnonzero', int64, int32, int64] = None

    out['awkward_reduce_countnonzero', int64, uint32, int64] = None

    out['awkward_reduce_countnonzero', int64, int64, int64] = None

    out['awkward_reduce_countnonzero', int64, uint64, int64] = None

    out['awkward_reduce_countnonzero', int64, float32, int64] = None

    out['awkward_reduce_countnonzero', int64, float64, int64] = None

    out['awkward_reduce_countnonzero_complex', int64, float32, int64] = None

    out['awkward_reduce_countnonzero_complex', int64, float64, int64] = None

    out['awkward_reduce_max', int8, int8, int64] = None

    out['awkward_reduce_max', uint8, uint8, int64] = None

    out['awkward_reduce_max', int16, int16, int64] = None

    out['awkward_reduce_max', uint16, uint16, int64] = None

    out['awkward_reduce_max', int32, int32, int64] = None

    out['awkward_reduce_max', uint32, uint32, int64] = None

    out['awkward_reduce_max', int64, int64, int64] = None

    out['awkward_reduce_max', uint64, uint64, int64] = None

    out['awkward_reduce_max', float32, float32, int64] = None

    out['awkward_reduce_max', float64, float64, int64] = None

    out['awkward_reduce_max_complex', float32, float32, int64] = None

    out['awkward_reduce_max_complex', float64, float64, int64] = None

    out['awkward_reduce_min', int8, int8, int64] = None

    out['awkward_reduce_min', uint8, uint8, int64] = None

    out['awkward_reduce_min', int16, int16, int64] = None

    out['awkward_reduce_min', uint16, uint16, int64] = None

    out['awkward_reduce_min', int32, int32, int64] = None

    out['awkward_reduce_min', uint32, uint32, int64] = None

    out['awkward_reduce_min', int64, int64, int64] = None

    out['awkward_reduce_min', uint64, uint64, int64] = None

    out['awkward_reduce_min', float32, float32, int64] = None

    out['awkward_reduce_min', float64, float64, int64] = None

    out['awkward_reduce_min_complex', float32, float32, int64] = None

    out['awkward_reduce_min_complex', float64, float64, int64] = None

    out['awkward_reduce_prod', int64, int8, int64] = None

    out['awkward_reduce_prod', uint64, uint8, int64] = None

    out['awkward_reduce_prod', int64, int16, int64] = None

    out['awkward_reduce_prod', uint64, uint16, int64] = None

    out['awkward_reduce_prod', int64, int32, int64] = None

    out['awkward_reduce_prod', uint64, uint32, int64] = None

    out['awkward_reduce_prod', int64, int64, int64] = None

    out['awkward_reduce_prod', uint64, uint64, int64] = None

    out['awkward_reduce_prod', float32, float32, int64] = None

    out['awkward_reduce_prod', float64, float64, int64] = None

    out['awkward_reduce_prod', int32, int8, int64] = None

    out['awkward_reduce_prod', uint32, uint8, int64] = None

    out['awkward_reduce_prod', int32, int16, int64] = None

    out['awkward_reduce_prod', uint32, uint16, int64] = None

    out['awkward_reduce_prod', int32, int32, int64] = None

    out['awkward_reduce_prod', uint32, uint32, int64] = None

    out['awkward_reduce_prod_complex', float32, float32, int64] = None

    out['awkward_reduce_prod_complex', float64, float64, int64] = None

    out['awkward_reduce_prod_bool', bool_, bool_, int64] = None

    out['awkward_reduce_prod_bool', bool_, int8, int64] = None

    out['awkward_reduce_prod_bool', bool_, uint8, int64] = None

    out['awkward_reduce_prod_bool', bool_, int16, int64] = None

    out['awkward_reduce_prod_bool', bool_, uint16, int64] = None

    out['awkward_reduce_prod_bool', bool_, int32, int64] = None

    out['awkward_reduce_prod_bool', bool_, uint32, int64] = None

    out['awkward_reduce_prod_bool', bool_, int64, int64] = None

    out['awkward_reduce_prod_bool', bool_, uint64, int64] = None

    out['awkward_reduce_prod_bool', bool_, float32, int64] = None

    out['awkward_reduce_prod_bool', bool_, float64, int64] = None

    out['awkward_reduce_prod_bool_complex', bool_, float32, int64] = None

    out['awkward_reduce_prod_bool_complex', bool_, float64, int64] = None

    out['awkward_reduce_sum', int64, int8, int64] = None

    out['awkward_reduce_sum', uint64, uint8, int64] = None

    out['awkward_reduce_sum', int64, int16, int64] = None

    out['awkward_reduce_sum', uint64, uint16, int64] = None

    out['awkward_reduce_sum', int64, int32, int64] = None

    out['awkward_reduce_sum', uint64, uint32, int64] = None

    out['awkward_reduce_sum', int64, int64, int64] = None

    out['awkward_reduce_sum', uint64, uint64, int64] = None

    out['awkward_reduce_sum', float32, float32, int64] = None

    out['awkward_reduce_sum', float64, float64, int64] = None

    out['awkward_reduce_sum', int32, int8, int64] = None

    out['awkward_reduce_sum', uint32, uint8, int64] = None

    out['awkward_reduce_sum', int32, int16, int64] = None

    out['awkward_reduce_sum', uint32, uint16, int64] = None

    out['awkward_reduce_sum', int32, int32, int64] = None

    out['awkward_reduce_sum', uint32, uint32, int64] = None

    out['awkward_reduce_sum', float64, int8, int64] = None

    out['awkward_reduce_sum', float64, uint8, int64] = None

    out['awkward_reduce_sum', float64, int16, int64] = None

    out['awkward_reduce_sum', float64, uint16, int64] = None

    out['awkward_reduce_sum', float64, int32, int64] = None

    out['awkward_reduce_sum', float64, uint32, int64] = None

    out['awkward_reduce_sum', float64, int64, int64] = None

    out['awkward_reduce_sum', float64, uint64, int64] = None

    out['awkward_reduce_sum', float64, float32, int64] = None

    out['awkward_reduce_sumofsquares', float64, int8, int64] = None

    out['awkward_reduce_sumofsquares', float64, uint8, int64] = None

    out['awkward_reduce_sumofsquares', float64, int16, int64] = None

    out['awkward_reduce_sumofsquares', float64, uint16, int64] = None

    out['awkward_reduce_sumofsquares', float64, int32, int64] = None

    out['awkward_reduce_sumofsquares', float64, uint32, int64] = None

    out['awkward_reduce_sumofsquares', float64, int64, int64] = None

    out['awkward_reduce_sumofsquares', float64, uint64, int64] = None

    out['awkward_reduce_sumofsquares', float64, bool_, int64] = None

    out['awkward_reduce_sumofsquares', float64, float32, int64] = None

    out['awkward_reduce_sumofsquares', float64, float64, int64] = None

    out['awkward_reduce_sumofpowers', float64, int8, int64] = None

    out['awkward_reduce_sumofpowers', float64, uint8, int64] = None

    out['awkward_reduce_sumofpowers', float64, int16, int64] = None

    out['awkward_reduce_sumofpowers', float64, uint16, int64] = None

    out['awkward_reduce_sumofpowers', float64, int32, int64] = None

    out['awkward_reduce_sumofpowers', float64, uint32, int64] = None

    out['awkward_reduce_sumofpowers', float64, int64, int64] = None

    out['awkward_reduce_sumofpowers', float64, uint64, int64] = None

    out['awkward_reduce_sumofpowers', float64, bool_, int64] = None

    out['awkward_reduce_sumofpowers', float64, float32, int64] = None

    out['awkward_reduce_sumofpowers', float64, float64, int64] = None

    out['awkward_reduce_centered_sumofsquares', float64, int8, int64, float64] = None

    out['awkward_reduce_centered_sumofsquares', float64, uint8, int64, float64] = None

    out['awkward_reduce_centered_sumofsquares', float64, int16, int64, float64] = None

    out['awkward_reduce_centered_sumofsquares', float64, uint16, int64, float64] = None

    out['awkward_reduce_centered_sumofsquares', float64, int32, int64, float64] = None

    out['awkward_reduce_centered_sumofsquares', float64, uint32, int64, float64] = None

    out['awkward_reduce_centered_sumofsquares', float64, int64, int64, float64] = None

    out['awkward_reduce_centered_sumofsquares', float64, uint64, int64, float64] = None

    out['awkward_reduce_centered_sumofsquares', float64, bool_, int64, float64] = None

    out['awkward_reduce_centered_sumofsquares', float64, float32, int64, float64] = None

    out['awkward_reduce_centered_sumofsquares', float64, float64, int64, float64] = None

    out['awkward_reduce_sum_complex', float32, float32, int64] = None

    out['awkward_reduce_sum_complex', float64, float64, int64] = None

    out['awkward_reduce_sum_bool', bool_, bool_, int64] = None

    out['awkward_reduce_sum_bool', bool_, int8, int64] = None

    out['awkward_reduce_sum_bool', bool_, uint8, int64] = None

    out['awkward_reduce_sum_bool', bool_, int16, int64] = None

    out['awkward_reduce_sum_bool', bool_, uint16, int64] = None

    out['awkward_reduce_sum_bool', bool_, int32, int64] = None

    out['awkward_reduce_sum_bool', bool_, uint32, int64] = None

    out['awkward_reduce_sum_bool', bool_, int64, int64] = None

    out['awkward_reduce_sum_bool', bool_, uint64, int64] = None

    out['awkward_reduce_sum_bool', bool_, float32, int64] = None

    out['awkward_reduce_sum_bool', bool_, float64, int64] = None

    out['awkward_reduce_sum_bool_complex', bool_, float32, int64] = None

    out['awkward_reduce_sum_bool_complex', bool_, float64, int64] = None

    out['awkward_reduce_sum_int32_bool_64', int32, bool_, int64] = None

    out['awkward_reduce_sum_int64_bool_64', int64, bool_, int64] = None

    out['awkward_sort', bool_, bool_, int64] = None

    out['awkward_sort', int8, int8, int64] = None

    out['awkward_sort', int16, int16, int64] = None

    out['awkward_sort', int32, int32, int64] = None

    out['awkward_sort', int64, int64, int64] = None

    out['awkward_sort', uint8, uint8, int64] = None

    out['awkward_sort', uint16, uint16, int64] = None

    out['awkward_sort', uint32, uint32, int64] = None

    out['awkward_sort', uint64, uint64, int64] = None

    out['awkward_sort', float32, float32, int64] = None

    out['awkward_sort', float64, float64, int64] = None

    out['awkward_unique_offsets', int8, int64, int64] = None

    out['awkward_unique_offsets', int16, int64, int64] = None

    out['awkward_unique_offsets', int32, int64, int64] = None

    out['awkward_unique_offsets', int64, int64, int64] = None

    out['awkward_unique_ranges_bool', bool_, int64, int64] = None

    out['awkward_unique_ranges', int8, int64, int64] = None

    out['awkward_unique_ranges', int16, int64, int64] = None

    out['awkward_unique_ranges', int32, int64, int64] = None

    out['awkward_unique_ranges', int64, int64, int64] = None

    out['awkward_unique_ranges', uint8, int64, int64] = None

    out['awkward_unique_ranges', uint16, int64, int64] = None

    out['awkward_unique_ranges', uint32, int64, int64] = None

    out['awkward_unique_ranges', uint64, int64, int64] = None

    out['awkward_unique_ranges', float32, int64, int64] = None

    out['awkward_unique_ranges', float64, int64, int64] = None

    def f(grid, block, args):
        (toindex, tolength, parents, parentslength, invocation_index, err_code) = args
        scan_in_array_k = cupy.ones(parentslength, dtype=cupy.int64)
        scan_in_array_j = cupy.zeros(parentslength, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_sorting_ranges_a', toindex.dtype, parents.dtype]))(grid, block, (toindex, tolength, parents, parentslength, scan_in_array_k, scan_in_array_j, invocation_index, err_code))
        scan_in_array_k = cupy.cumsum(scan_in_array_k)
        scan_in_array_j = cupy.cumsum(scan_in_array_j)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_sorting_ranges_b', toindex.dtype, parents.dtype]))(grid, block, (toindex, tolength, parents, parentslength, scan_in_array_k, scan_in_array_j, invocation_index, err_code))
    out["awkward_sorting_ranges_a", int64, int64] = None
    out["awkward_sorting_ranges_b", int64, int64] = None
    f.dir = ['out', 'in', 'in', 'in']
    f.is_ptr = [True, False, True, False]
    out['awkward_sorting_ranges', int64, int64] = f

    def f(grid, block, args):
        (tolength, parents, parentslength, invocation_index, err_code) = args
        scan_in_array = cupy.zeros(parentslength, dtype=cupy.int64)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_sorting_ranges_length_a', tolength.dtype, parents.dtype]))(grid, block, (tolength, parents, parentslength, scan_in_array, invocation_index, err_code))
        scan_in_array = cupy.cumsum(scan_in_array)
        cuda_kernel_templates.get_function(fetch_specialization(['awkward_sorting_ranges_length_b', tolength.dtype, parents.dtype]))(grid, block, (tolength, parents, parentslength, scan_in_array, invocation_index, err_code))
    out["awkward_sorting_ranges_length_a", int64, int64] = None
    out["awkward_sorting_ranges_length_b", int64, int64] = None
    f.dir = ['out', 'in', 'in']
    f.is_ptr = [True, True, False]
    out['awkward_sorting_ranges_length', int64, int64] = f

    return out
