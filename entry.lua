-- HD2-Addon: mods/suzuka/extra_slot
-- M-103 appears as a separate mission stratagem through Reinforcement's additional_stratagem field.
if rawget(_G,'SuzukasExtraSlot') then return end

local loader=rawget(_G,'CowboyBingusModLoader')
local state={version='1.0.0',status='WAITING',attempts=0,writes=0}
rawset(_G,'SuzukasExtraSlot',state)

local api_factory=(function()
__MEMORY_API__
end)()

local game_sha='__GAME_SHA__'
local expected=__EXPECTED_IDS__
local groups=__EXPECTED_GROUPS__
local m103_package=__M103_PACKAGE_BYTES__
local m103_icon=__M103_ICON_BYTES__
local target_before=string.char(0,0,0,0)
local target_after=string.char(26,0,0,0)
local api,game,settings,record_address,original_record

local function log()
    pcall(function()
        local file=loader and loader.open_log and loader.open_log('SuzukasExtraSlot.log')
        if not file then return end
        file:write('VERSION='..state.version..'\nSTATUS='..state.status..'\n')
        file:write('ATTEMPTS='..state.attempts..' WRITES='..state.writes..'\n')
        file:write('GAME_SHA='..game_sha..'\n')
        file:write('METHOD=REINFORCEMENT_ADDITIONAL_STRATAGEM_M103\n')
        file:close()
    end)
end

local function u32(bytes,at)
    local a,b,c,d=bytes:byte(at+1,at+4)
    assert(d,'short_u32')
    return a+b*256+c*65536+d*16777216
end

local function pointer(bytes,at)
    local value=api.pointer(bytes:sub(at+1,at+8))
    assert(value,'invalid_pointer')
    return value
end

local function prepare()
    api=api or api_factory()
    game=api.module('game.dll')
    assert(game,'game_dll_missing')
    assert(api.module_hash(game)==game_sha,'unsupported_game_dll_no_write')
    local ptr_bytes=assert(api.read_module(game+0x348e8f8,8),'settings_pointer_unreadable')
    local buffer=pointer(ptr_bytes,0)
    local source=assert(api.read_blob(buffer,80280),'settings_not_ready')
    assert(u32(source,0)==11,'group_count_mismatch')
    local offset,seen,rearm=4,{},0
    local reinforcement,m103
    for group=1,11 do
        assert(u32(source,offset)==0x444c444c and u32(source,offset+4)==1,'dl_header_mismatch')
        assert(u32(source,offset+8)==groups[group][1]
            and u32(source,offset+12)==groups[group][2]
            and u32(source,offset+16)==1 and u32(source,offset+20)==0,'dl_group_mismatch')
        local root=offset+24
        local finish=root+groups[group][2]
        assert(finish<=#source,'group_bounds')
        local count=u32(source,root+8)
        assert(count==groups[group][3],'record_count_mismatch')
        local start=pointer(source,root)-buffer
        assert(start>=root+16 and start+count*400<=finish,'record_pointer_bounds')
        for i=0,count-1 do
            local at=start+i*400
            local kind,id=u32(source,at),u32(source,at+4)
            assert(expected[kind]==id and not seen[kind],'stratagem_identity_mismatch')
            seen[kind]=true
            local extra=u32(source,at+200)
            if extra~=0 then
                assert(extra==49,'unexpected_additional_stratagem')
                rearm=rearm+1
            end
            if kind==124 then reinforcement=at end
            if kind==26 then m103=at end
        end
        offset=finish
    end
    assert(offset==#source and #expected==149 and rearm==10,'incomplete_stratagem_table')
    assert(reinforcement and m103,'target_missing')
    assert(u32(source,reinforcement+4)==2266266587
        and u32(source,reinforcement+200)==0,'reinforcement_original_mismatch')
    assert(u32(source,m103+4)==2636699686 and u32(source,m103+200)==0,'m103_identity_mismatch')
    assert(source:sub(m103+169,m103+176)==m103_package,'m103_package_mismatch')
    assert(source:sub(m103+177,m103+184)==m103_icon,'m103_icon_mismatch')
    local target=buffer+reinforcement+200
    local region=assert(api.query(target),'target_region_unavailable')
    assert(region.kind==0x20000 and region.protection==4,'target_not_private_writable')
    assert(api.read_module(game+0x348e8f8,8)==ptr_bytes,'settings_pointer_changed')
    assert(api.read_blob(buffer,80280)==source,'settings_changed')
    return buffer,target,source:sub(reinforcement+1,reinforcement+400)
end

local previous_update=rawget(_G,'update')
local ticks=0
local function install()
    state.attempts=state.attempts+1
    local ok,buffer,target,before=pcall(prepare)
    if not ok then
        state.status=tostring(buffer)
        log()
        return state.status:find('settings_not_ready',1,true)~=nil
    end
    local written,details=api.write(target,target_after)
    if not written then
        state.status='WRITE_FAILED '..tostring(details)
        log()
        return false
    end
    settings,record_address,original_record=buffer,target,before
    state.status='APPLIED_ADDITIONAL_M103_READBACK_VERIFIED'
    state.writes=1
    log()
    return false
end

local function pack(...) return {n=select('#',...),...} end
if type(previous_update)=='function' then
    local wrapper
    wrapper=function(...)
        local result=pack(previous_update(...))
        ticks=ticks+1
        if state.status=='WAITING' and ticks%60==0 and ticks<=1200 then
            local retry=install()
            if retry then state.status='WAITING' end
        end
        if ticks>=1200 and state.status=='WAITING' then
            state.status='TIMEOUT_NO_WRITE';log()
        end
        if state.status~='WAITING' and rawget(_G,'update')==wrapper then
            rawset(_G,'update',previous_update)
        end
        return unpack(result,1,result.n)
    end
    rawset(_G,'update',wrapper)
end

local previous_shutdown=rawget(_G,'shutdown')
rawset(_G,'shutdown',function(...)
    if state.writes==1 and api and game and settings and record_address and original_record then
        local current=api.read(record_address-200,400)
        local modified=original_record:sub(1,200)..target_after..original_record:sub(205)
        if current==modified then
            local ok=api.write(record_address,target_before)
            state.status=ok and 'RESTORED_ON_SHUTDOWN' or 'RESTORE_FAILED'
            log()
        end
    end
    if previous_shutdown then return previous_shutdown(...) end
end)

log()
