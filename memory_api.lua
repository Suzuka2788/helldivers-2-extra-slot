-- Windows API adapter for a single, guarded M-103 extra slot.
return function()
    local ffi=require('ffi')
    assert(ffi.os=='Windows' and ffi.abi('64bit'),'windows_x64_required')
    ffi.cdef[[
        void *GetModuleHandleA(const char *);
        uint32_t GetModuleFileNameW(void *,uint16_t *,uint32_t);
        void *GetCurrentProcess(void);
        int ReadProcessMemory(void *,const void *,void *,size_t,size_t *);
        int WriteProcessMemory(void *,void *,const void *,size_t,size_t *);
        size_t VirtualQuery(const void *,void *,size_t);
        int VirtualProtect(void *,size_t,uint32_t,uint32_t *);
        uint32_t GetLastError(void);
        void *CreateFileW(const uint16_t *,uint32_t,uint32_t,void *,uint32_t,uint32_t,void *);
        int ReadFile(void *,void *,uint32_t,uint32_t *,void *);
        int CloseHandle(void *);
        int32_t BCryptOpenAlgorithmProvider(void **,const uint16_t *,const uint16_t *,uint32_t);
        int32_t BCryptCreateHash(void *,void **,void *,uint32_t,const void *,uint32_t,uint32_t);
        int32_t BCryptHashData(void *,const void *,uint32_t,uint32_t);
        int32_t BCryptFinishHash(void *,void *,uint32_t,uint32_t);
        int32_t BCryptDestroyHash(void *);
        int32_t BCryptCloseAlgorithmProvider(void *,uint32_t);
        typedef struct { void *base; void *allocation; uint32_t protection0;
            uint16_t partition; uint16_t reserved; size_t size;
            uint32_t state; uint32_t protection; uint32_t kind; } SuzukaMemoryRegion;
    ]]
    local k,b=ffi.load('kernel32'),ffi.load('bcrypt')
    local process=k.GetCurrentProcess()
    local api={}
    local scan_buffer=ffi.new('uint8_t[262144]')
    local scan_count=ffi.new('size_t[1]')
    local scan_address=tonumber(ffi.cast('uintptr_t',scan_buffer))
    function api.excluded(address,size)
        return address<scan_address+262144 and address+size>scan_address
    end
    function api.query(address)
        if address>=0x800000000000 then return nil,'end' end
        local info=ffi.new('SuzukaMemoryRegion[1]')
        if k.VirtualQuery(ffi.cast('void *',address),info,ffi.sizeof(info[0]))~=ffi.sizeof(info[0]) then
            return nil,k.GetLastError()==87 and 'end' or 'query_failed'
        end
        local r=info[0]
        local p=tonumber(r.protection)%256
        local kind=tonumber(r.kind)
        return {base=tonumber(ffi.cast('uintptr_t',r.base)),allocation=tonumber(ffi.cast('uintptr_t',r.allocation)),size=tonumber(r.size),
            protection=tonumber(r.protection),
            readable=r.state==0x1000 and (kind==0x20000 or kind==0x40000)
                and (p==2 or p==4 or p==8 or p==32 or p==64 or p==128)
                and tonumber(r.protection)<256,kind=kind}
    end
    function api.read_blob(address,size)
        if type(size)~='number' or size<=0 or size>262144 or api.excluded(address,size) then return nil end
        local r=api.query(address)
        if not r or not r.readable or address<r.base or address+size>r.base+r.size then return nil end
        if k.ReadProcessMemory(process,ffi.cast('const void *',address),scan_buffer,size,scan_count)==0
            or tonumber(scan_count[0])~=size then return nil end
        return ffi.string(scan_buffer,size)
    end
    -- Read-only bulk access for committed module-image pages. General memory
    -- scanners intentionally exclude MEM_IMAGE; layout migration needs to
    -- inspect game.dll's own global-pointer slots without enabling writes.
    function api.read_module(address,size)
        if type(size)~='number' or size<=0 or size>262144 or api.excluded(address,size) then return nil end
        local r=api.query(address)
        if not r or r.kind~=0x1000000 or address<r.base or address+size>r.base+r.size
            or r.protection>=256 then return nil end
        local p=r.protection%256
        if p~=2 and p~=4 and p~=8 and p~=32 and p~=64 and p~=128 then return nil end
        if k.ReadProcessMemory(process,ffi.cast('const void *',address),scan_buffer,size,scan_count)==0
            or tonumber(scan_count[0])~=size then return nil end
        return ffi.string(scan_buffer,size)
    end
    function api.module(name)
        local p=k.GetModuleHandleA(name)
        if p==nil or p==ffi.NULL then return nil end
        return tonumber(ffi.cast('uintptr_t',p))
    end
    function api.pointer(bytes)
        if not bytes or #bytes~=8 then return nil end
        local p=ffi.new('uint64_t[1]')
        ffi.copy(p,bytes,8)
        if p[0]<65536 or p[0]>=0x800000000000 then return nil end
        return tonumber(p[0])
    end
    local function region(address,size)
        if type(address)~='number' or type(size)~='number' or size<=0
            or address<65536 or address+size>=0x800000000000 then return nil end
        local info=ffi.new('SuzukaMemoryRegion[1]')
        if k.VirtualQuery(ffi.cast('void *',address),info,ffi.sizeof(info[0]))~=ffi.sizeof(info[0]) then return nil end
        local r=info[0]
        local base=tonumber(ffi.cast('uintptr_t',r.base))
        local protection=tonumber(r.protection)
        if r.state~=0x1000 or address<base or address+size>base+tonumber(r.size)
            or (r.kind~=0x20000 and r.kind~=0x40000 and r.kind~=0x1000000)
            or protection>=256 then return nil end
        return protection,tonumber(r.kind)
    end
    function api.read(address,size)
        if size>4096 or not region(address,size) then return nil end
        local out,count=ffi.new('uint8_t[?]',size),ffi.new('size_t[1]')
        if k.ReadProcessMemory(process,ffi.cast('const void *',address),out,size,count)==0
            or tonumber(count[0])~=size then return nil end
        return ffi.string(out,size)
    end
    function api.write(address,bytes)
        if type(bytes)~='string' or (#bytes~=1 and #bytes~=4 and #bytes~=8 and #bytes~=12
            and #bytes~=16 and #bytes~=24 and #bytes~=268) then
            return false,'invalid_size'
        end
        local protection,kind=region(address,#bytes)
        -- PAGE_WRITECOPY (8) is a non-executable data page used by some
        -- runtime resource snapshots. Allow it with the same guarded
        -- VirtualProtect/write/readback path as PAGE_READONLY.
        if (protection~=2 and protection~=4 and protection~=8) or kind==0x1000000 then
            return false,'not_plain_data_page'
        end
        local before=api.read(address,#bytes)
        if not before then return false,'before_read_failed' end
        local changed=false
        local old=ffi.new('uint32_t[1]')
        if protection~=4 then
            if k.VirtualProtect(ffi.cast('void *',address),#bytes,4,old)==0 then
                return false,'make_writable_failed_'..tonumber(k.GetLastError())
            end
            changed=true
        end
        local count=ffi.new('size_t[1]')
        local ok=k.WriteProcessMemory(process,ffi.cast('void *',address),bytes,#bytes,count)~=0
            and tonumber(count[0])==#bytes
        local write_error=ok and 0 or tonumber(k.GetLastError())
        local restored=true
        if changed then
            local ignored=ffi.new('uint32_t[1]')
            restored=k.VirtualProtect(ffi.cast('void *',address),#bytes,old[0],ignored)~=0
        end
        local after=api.read(address,#bytes)
        return ok and restored and after==bytes,
            string.format('written=%d error=%d restored=%s readback=%s',
                tonumber(count[0]),write_error,tostring(restored),tostring(after==bytes))
    end
    function api.module_hash(address)
        local cached=rawget(_G,'SuzukaVerifiedGameDllHash')
        if type(cached)=='table' and cached.address==address
            and type(cached.sha256)=='string' and #cached.sha256==64 then
            return cached.sha256
        end
        local path=ffi.new('uint16_t[32768]')
        local n=k.GetModuleFileNameW(ffi.cast('void *',address),path,32768)
        assert(n>0 and n<32768,'game_dll_path_unavailable')
        local file=k.CreateFileW(path,0x80000000,7,nil,3,0x08000000,nil)
        assert(file~=ffi.cast('void *',-1),'game_dll_file_unavailable')
        local algorithm,hash=ffi.new('void *[1]'),ffi.new('void *[1]')
        local ok,result=pcall(function()
            local name=ffi.new('uint16_t[7]',{83,72,65,50,53,54,0})
            assert(b.BCryptOpenAlgorithmProvider(algorithm,name,nil,0)==0,'sha256_provider')
            assert(b.BCryptCreateHash(algorithm[0],hash,nil,0,nil,0,0)==0,'sha256_create')
            local chunk,count=ffi.new('uint8_t[65536]'),ffi.new('uint32_t[1]')
            local total=0
            while true do
                assert(k.ReadFile(file,chunk,65536,count,nil)~=0,'game_dll_read')
                if count[0]==0 then break end
                total=total+tonumber(count[0])
                assert(total<=64*1024*1024,'game_dll_too_large')
                assert(b.BCryptHashData(hash[0],chunk,count[0],0)==0,'sha256_update')
            end
            local digest,parts=ffi.new('uint8_t[32]'),{}
            assert(b.BCryptFinishHash(hash[0],digest,32,0)==0,'sha256_finish')
            for i=0,31 do parts[#parts+1]=string.format('%02x',digest[i]) end
            return table.concat(parts)
        end)
        if hash[0]~=nil then b.BCryptDestroyHash(hash[0]) end
        if algorithm[0]~=nil then b.BCryptCloseAlgorithmProvider(algorithm[0],0) end
        k.CloseHandle(file)
        assert(ok,result)
        rawset(_G,'SuzukaVerifiedGameDllHash',{address=address,sha256=result})
        return result
    end
    return api
end
