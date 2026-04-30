"""DynaPath Mobile SDK token generator - ported from Korail Talk APK"""
import math
import random
import string
import time
import urllib.parse


CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

_primes_cache = {}
_order_table_cache = {}


def _generate_primes(count):
    if count in _primes_cache:
        return _primes_cache[count]
    primes = [2]
    n = 3
    while len(primes) < count + 1:
        sqrt_n = int(math.sqrt(n))
        is_prime = True
        for p in primes:
            if p > sqrt_n:
                break
            if n % p == 0:
                is_prime = False
                break
        if is_prime:
            primes.append(n)
        n += 1
    primes.pop(0)  # remove 2
    result = primes[:count]
    _primes_cache[count] = result
    return result


def _get_primes():
    return _generate_primes(100)


def _get_order_table(num):
    if isinstance(num, int):
        key = num
    else:
        key = num % 841

    if key in _order_table_cache:
        return _order_table_cache[key]

    primes = _get_primes()
    p1 = primes[key % 29]
    p2 = primes[(key // 29) % 29]
    table = _fix_table(CHARSET, p1, p2)
    _order_table_cache[key] = table
    return table


def _next_prime_le(n):
    """Find the largest prime <= n from the prime list."""
    primes = _get_primes()
    result = 1
    for p in primes:
        if p > n:
            break
        result = p
    return result


def _fix_table(s, p1, p2):
    length = len(s)
    d = _next_prime_le(length)
    visited = [0] * d
    result = ['\0'] * d
    big = 1
    val_p1 = p1
    val_p2 = p2

    for i in range(d):
        idx = ((big % d) * val_p2) % d
        visited[idx] += 1
        if visited[idx] == 1:
            result[i] = s[idx]
        big = big * val_p1

    sb_main = []
    sb_rest = []
    for i in range(d):
        if result[i] == '\0':
            for j in range(d):
                if visited[j] == 0:
                    result[i] = s[j]
                    sb_rest.append(s[j])
                    visited[j] = 1
                    break
        else:
            sb_main.append(result[i])

    for i in range(d, length):
        sb_rest.append(s[i])

    rest_str = ''.join(sb_rest)
    primes = _get_primes()
    if len(rest_str) < primes[0]:
        return ''.join(sb_main) + rest_str
    else:
        return ''.join(sb_main) + _fix_table(rest_str, p1, p2)


def _string_to_xa1s(s):
    result = []
    for ch in s:
        cp = ord(ch)
        if cp < 128:
            result.append(cp)
        elif cp < 2048:
            result.append(128 | ((cp >> 7) & 15))
            result.append(cp & 127)
        elif cp >= 262144:
            result.append(160)
            result.append((cp >> 14) & 127)
            result.append((cp >> 7) & 127)
            result.append(cp & 127)
        elif (63488 & cp) != 55296:
            result.append(((cp >> 14) & 15) | 144)
            result.append((cp >> 7) & 127)
            result.append(cp & 127)
    return result


def _make_key(key_str):
    result = 0
    for ch in key_str:
        cp = ord(ch)
        i9 = 32768
        for _ in range(16):
            if (i9 & cp) != 0:
                break
            i9 >>= 1
        result = result * (i9 << 1) + cp
    return result


def _encode_normal_be(s, table, decode, encode, block):
    xa1s = _string_to_xa1s(str(s))
    sb = []
    buf = [0] * (block + 1)
    remainder = len(xa1s) % block
    main_len = len(xa1s) - remainder
    i = 0

    while i < main_len:
        val = 0
        for _ in range(block):
            val = val * decode + xa1s[i]
            i += 1
        for j in range(block + 1):
            buf[j] = int(val % encode)
            val = val // encode
        for j in range(block, -1, -1):
            sb.append(table[buf[j]])

    if remainder > 0:
        val = 0
        for k in range(remainder):
            val = val * decode + xa1s[i]
            i += 1
        for j in range(remainder + 1):
            buf[j] = int(val % encode)
            val = val // encode
        for j in range(remainder, -1, -1):
            sb.append(table[buf[j]])

    return ''.join(sb)


def _sizes_by_index(i, j):
    sizes = [30, 46, 59]
    block = 2
    for s in sizes:
        gap = 63 - s
        if j < gap:
            break
        j -= gap
        block += 1
    else:
        s = sizes[-1]
    return (i, s + j, block)  # decode, encode, block


def prime_encode(org, key=None):
    decode, encode, block = _sizes_by_index(161, 0)

    is_str = isinstance(org, str)

    if key is None:
        i8 = (1 if is_str else 0) % 10
        order_table = _get_order_table(i8)
        header = (
            str(chr(i8 + 48))
            + order_table[decode // 62]
            + order_table[decode % 62]
            + order_table[block]
            + order_table[encode - 1]
        )
        return header + _encode_normal_be(org, order_table, decode, encode, block)

    if not isinstance(key, str):
        return ""

    i9 = (1 if is_str else 0) % 26
    order_table2 = _get_order_table(i9)
    header = (
        str(chr(i9 + 97))
        + order_table2[decode // 62]
        + order_table2[decode % 62]
        + order_table2[block]
        + order_table2[encode - 1]
    )
    encoded_key = _encode_normal_be(key, order_table2, decode, encode, block)
    header += order_table2[len(encoded_key)]
    header += encoded_key

    key_big = _make_key(key)
    encode_table = _make_encode_table(key_big, encode, order_table2)
    encoded_data = _encode_normal_be(org, encode_table, decode, encode, block)

    return header + encoded_data


def _make_encode_table(num, size, order_table=None):
    if order_table is None:
        order_table = _get_order_table_big(num)
        num = num // 841

    sb = []
    for i in range(size):
        remaining = size - i
        idx = num % remaining
        ch = _find_char(order_table, idx, size, ''.join(sb))
        sb.append(ch)
        num = num // remaining
    return ''.join(sb)


def _get_order_table_big(num):
    return _get_order_table(num % 841)


def _find_char(table, target, size, already):
    count = 0
    for i in range(size):
        if table[i] not in already:
            if count == target:
                return table[i]
            count += 1
    return ' '


def generate_token(
    app_id="com.korail.talk",
    device_id=None,
    app_signature=None,
    os_version="14",
    device_model="SM-S912N",
    is_root=False,
    is_debug=False,
    is_emulator=False,
    is_hooked=False,
):
    now = int(time.time() * 1000)

    if device_id is None:
        device_id = ''.join(random.choices('0123456789abcdef', k=16))

    if app_signature is None:
        app_signature = ''.join(random.choices('0123456789ABCDEF', k=64))

    params = {}
    params['ai'] = app_id
    params['di'] = device_id
    params['as'] = app_signature
    params['su'] = str(is_root).lower()
    params['dbg'] = str(is_debug).lower()
    params['emu'] = str(is_emulator).lower()
    params['hk'] = str(is_hooked).lower()
    params['it'] = str(now)
    params['ts'] = str(now)
    params['rt'] = str(now)
    params['os'] = os_version
    params['dm'] = device_model
    params['st'] = 'Android'
    params['sv'] = 'v1'

    query = '&'.join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in params.items()
    )

    rand_chars = ''.join(random.choices(string.ascii_letters + string.digits, k=4))
    key = f"v1+{rand_chars}+{now}"

    return prime_encode(query, key)


if __name__ == "__main__":
    token = generate_token()
    print(f"Token length: {len(token)}")
    print(f"Token: {token[:100]}...")