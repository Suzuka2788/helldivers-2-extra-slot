-- Offline stand-in for memory_api.lua. Memory is a table of Lua strings owned by the
-- test (SuzukaFake.memory[base]=bytes); no process memory is touched.
return function()
    local f=assert(rawget(_G,'SuzukaFake'),'fake_missing')
    local api={}
    local function le64(value)
        local bytes={}
        for i=1,8 do bytes[i]=string.char(value%256);value=math.floor(value/256) end
        return table.concat(bytes)
    end
    local function locate(address,size)
        for base,bytes in pairs(f.memory) do
            local offset=address-base
            if offset>=0 and offset+size<=#bytes then return base,offset end
        end
    end
    function api.module(name) if name=='game.dll' then return f.game end end
    function api.module_hash() return f.sha end
    function api.read_module(address,size)
        f.reads=f.reads+1
        if address==f.game+0x348e8f8 and size==8 and f.slot then return le64(f.slot) end
    end
    function api.pointer(bytes)
        if not bytes or #bytes~=8 then return nil end
        local value=0
        for i=8,1,-1 do value=value*256+bytes:byte(i) end
        if value<65536 then return nil end
        return value
    end
    function api.read_blob(address,size)
        f.reads=f.reads+1
        local bytes=f.memory[address]
        if bytes and #bytes==size then return bytes end
    end
    function api.read(address,size)
        f.reads=f.reads+1
        local base,offset=locate(address,size)
        if base then return f.memory[base]:sub(offset+1,offset+size) end
    end
    function api.query() return {kind=f.kind,protection=f.protection} end
    function api.write(address,bytes)
        f.writes[#f.writes+1]={address=address,bytes=bytes}
        if f.fail_write then return false,'fake_failure' end
        local base,offset=locate(address,#bytes)
        if not base then return false,'unmapped' end
        local old=f.memory[base]
        f.memory[base]=old:sub(1,offset)..bytes..old:sub(offset+#bytes+1)
        return true,'fake_ok'
    end
    return api
end
