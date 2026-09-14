-- Announce which FSRCNNX model is active. No other shaders.

local function label_from(shaders)
    shaders = shaders or ""
    if shaders:find("16%-0%-4%-1", 1, false) then
        return "FSRCNNX-16"
    end
    if shaders:find("8%-0%-4%-1", 1, false) then
        return "FSRCNNX-8"
    end
    if shaders == "" then
        return "None — native (no AI)"
    end
    return nil
end

local function announce()
    local name = label_from(mp.get_property("glsl-shaders"))
    if name then
        mp.osd_message(name, 2)
    end
end

mp.register_event("file-loaded", announce)
