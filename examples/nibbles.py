byte = 0xA5
hex_chars = "0123456789ABCDEF"
high = (byte >> 4) & 0x0F
low = byte & 0x0F

full = hex_chars[high] + hex_chars[low]

print(f"Byte: {byte:#04x} ({full}), High nibble: {high}, Low nibble: {low}")
