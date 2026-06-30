"""Minimal pure-Python BSON decoder (no external deps) + TTS save analyzer."""
import struct, sys, json

class BSONError(Exception):
    pass

def _cstring(buf, i):
    j = buf.index(b'\x00', i)
    return buf[i:j].decode('utf-8', 'replace'), j + 1

def _read_doc(buf, i):
    """Return (dict_or_list, new_index). Arrays (0x04) returned as list."""
    start = i
    (length,) = struct.unpack_from('<i', buf, i)
    end = start + length
    i += 4
    items = []  # (key, value)
    while i < end - 1:
        etype = buf[i]; i += 1
        key, i = _cstring(buf, i)
        if etype == 0x01:      # double
            (v,) = struct.unpack_from('<d', buf, i); i += 8
        elif etype == 0x02:    # string
            (slen,) = struct.unpack_from('<i', buf, i); i += 4
            v = buf[i:i+slen-1].decode('utf-8', 'replace'); i += slen
        elif etype == 0x03:    # embedded document
            v, i = _read_doc(buf, i)
        elif etype == 0x04:    # array
            v, i = _read_doc(buf, i)
        elif etype == 0x05:    # binary
            (blen,) = struct.unpack_from('<i', buf, i); i += 4
            subtype = buf[i]; i += 1
            v = buf[i:i+blen]; i += blen
            v = {'$binary_len': blen, '$subtype': subtype}
        elif etype == 0x08:    # bool
            v = bool(buf[i]); i += 1
        elif etype == 0x09:    # UTC datetime int64
            (v,) = struct.unpack_from('<q', buf, i); i += 8
        elif etype == 0x0A:    # null
            v = None
        elif etype == 0x10:    # int32
            (v,) = struct.unpack_from('<i', buf, i); i += 4
        elif etype == 0x11:    # timestamp uint64
            (v,) = struct.unpack_from('<Q', buf, i); i += 8
        elif etype == 0x12:    # int64
            (v,) = struct.unpack_from('<q', buf, i); i += 8
        elif etype == 0x00:
            break
        else:
            raise BSONError(f"Unknown BSON element type 0x{etype:02x} for key {key!r} at {i}")
        items.append((key, v))
    # decide list vs dict: array element keys are "0","1","2",...
    if items and all(k == str(n) for n, (k, _) in enumerate(items)):
        return [v for _, v in items], end
    return {k: v for k, v in items}, end

def decode_file(path):
    with open(path, 'rb') as f:
        buf = f.read()
    doc, end = _read_doc(buf, 0)
    return doc, len(buf), end

if __name__ == '__main__':
    path = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else None
    doc, total, consumed = decode_file(path)
    sys.stderr.write(f"decoded ok: total_bytes={total} consumed={consumed} "
                     f"clean={'YES' if consumed==total else 'NO'}\n")
    if out:
        with open(out, 'w') as f:
            json.dump(doc, f)
        sys.stderr.write(f"wrote JSON -> {out}\n")
