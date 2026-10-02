-- HD2-Addon: mods/suzuka/extra_slot
-- One free extra mission stratagem through Reinforcement's additional_stratagem field.
-- Every native read and write runs inside the global update/shutdown callbacks on the
-- game's Lua thread. select() only queues a choice for the next update; the in-game
-- MODS menu (Mod Options Menu, see MOD_OPTIONS_MENU_NOTES.md) calls it on APPLY.
if rawget(_G,'SuzukasExtraSlot') then return end

-- Captured at load so another addon replacing these globals cannot break the callbacks.
local pcall,type,tostring,tonumber,select,rawget,rawset=pcall,type,tostring,tonumber,select,rawget,rawset
local unpack=unpack or table.unpack

local loader=rawget(_G,'CowboyBingusModLoader')
local state={version='__VERSION__',status='WAITING',attempts=0,writes=0,restores=0,history={}}
rawset(_G,'SuzukasExtraSlot',state)

local api_factory=(function()
__MEMORY_API__
end)()

local game_sha='__GAME_SHA__'
local expected=__EXPECTED_IDS__
local groups=__EXPECTED_GROUPS__
local choices=__CHOICES__
local initial_key='__INITIAL_KEY__'
local REINFORCEMENT,REINFORCEMENT_ID=124,2266266587
local FIELD,RECORD=200,400
local SETTINGS_SLOT,SETTINGS_SIZE=0x348e8f8,80280
local RETRY_TICKS,GIVE_UP_TICKS,WATCH_TICKS=60,1200,600
-- Failures that happen while the table is loading or moving; everything else stops writes.
local TRANSIENT={settings_not_ready=true,settings_pointer_unreadable=true,invalid_pointer=true,
    settings_pointer_changed=true,settings_changed=true,game_dll_missing=true}
-- Explanations written to the log for failures a player can act on.
local HINTS={
    unsupported_game_dll_no_write='Helldivers 2 was updated. This build supports only GAME_SHA; '
        ..'nothing was written. Wait for an updated Extra Slot.',
    reinforcement_foreign_value='Another mod already changed Reinforcement additional_stratagem. '
        ..'Disable the older M-103 / Extra Slot package or the other mod; nothing was written.',
    foreign_write_detected='Another mod changed the free stratagem after this mod wrote it. '
        ..'This mod stopped and will not restore it. Disable the other mod.',
}

local by_key={}
state.choices={}
for i,choice in ipairs(choices) do
    by_key[choice.key]=choice
    state.choices[i]={key=choice.key,name=choice.name}
end

local api,game
local owned -- {ptr_bytes,address,original,value}: the field value this addon wrote and still owns
-- The value written into a table that has since been replaced. A replacement table copied
-- from the old one may still hold it; it is then taken over instead of treated as foreign.
local carried
-- Keeps the menu in step with select(); set once the menu is registered.
local sync_menu=function() end
local pending,pending_since,pending_next,halted
local ticks=0
state.menu='WAITING'

-- Adds a history line and rewrites the log; STATUS keeps the last write-path result.
local function event(text)
    local history=state.history
    history[#history+1]=ticks..' '..text
    if #history>16 then table.remove(history,1) end
    pcall(function()
        local file=loader and loader.open_log and loader.open_log('SuzukasExtraSlot.log')
        if not file then return end
        file:write('VERSION='..state.version..'\nSTATUS='..state.status..'\n')
        file:write('ATTEMPTS='..state.attempts..' WRITES='..state.writes..' RESTORES='..state.restores..'\n')
        file:write('GAME_SHA='..game_sha..'\n')
        if state.game_sha_seen then file:write('GAME_SHA_SEEN='..state.game_sha_seen..'\n') end
        file:write('METHOD=REINFORCEMENT_ADDITIONAL_STRATAGEM\n')
        file:write('INITIAL='..initial_key..' SELECTED='..tostring(state.selected)
            ..' APPLIED='..tostring(state.applied)..'\nMENU='..state.menu
            ..(state.menu_ui and ' UI='..state.menu_ui or '')..'\n')
        if state.hint then file:write('HINT='..state.hint..'\n') end
        file:write('HISTORY:\n'..table.concat(history,'\n')..'\n')
        file:close()
    end)
end

local function note(status)
    state.status=status
    event(status)
end

-- Lua 5.1 assert prefixes 'chunk:line: '; keep only the reason.
local function reason(err)
    return (tostring(err):gsub('^.-:%d+: ',''))
end

local function u32(bytes,at)
    local a,b,c,d=bytes:byte(at+1,at+4)
    assert(d,'short_u32')
    return a+b*256+c*65536+d*16777216
end

local function le32(value)
    return string.char(value%256,math.floor(value/256)%256,
        math.floor(value/65536)%256,math.floor(value/16777216)%256)
end

local function with_field(record,value)
    return record:sub(1,FIELD)..le32(value)..record:sub(FIELD+5)
end

local function pointer(bytes,at)
    local value=api.pointer(bytes:sub(at+1,at+8))
    assert(value,'invalid_pointer')
    return value
end

-- Validates the game build and the complete stratagem table. Reinforcement may hold 0 or
-- the value this addon still owns; any other value belongs to something else.
local function check_game()
    api=api or api_factory()
    game=api.module('game.dll')
    assert(game,'game_dll_missing')
    local seen=api.module_hash(game)
    if seen~=game_sha then
        state.game_sha_seen=tostring(seen)
        error('unsupported_game_dll_no_write',0)
    end
end

local function prepare()
    check_game()
    local ptr_bytes=assert(api.read_module(game+SETTINGS_SLOT,8),'settings_pointer_unreadable')
    local buffer=pointer(ptr_bytes,0)
    local source=assert(api.read_blob(buffer,SETTINGS_SIZE),'settings_not_ready')
    local mine
    if owned and owned.ptr_bytes==ptr_bytes then mine=owned.value else mine=carried end
    assert(u32(source,0)==11,'group_count_mismatch')
    local offset,at,rearm=4,{},0
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
        assert(start>=root+16 and start+count*RECORD<=finish,'record_pointer_bounds')
        for i=0,count-1 do
            local record=start+i*RECORD
            local kind,id=u32(source,record),u32(source,record+4)
            assert(expected[kind]==id and not at[kind],'stratagem_identity_mismatch')
            at[kind]=record
            local extra=u32(source,record+FIELD)
            if kind==REINFORCEMENT then
                assert(extra==0 or extra==mine,'reinforcement_foreign_value')
            elseif extra~=0 then
                assert(extra==49,'unexpected_additional_stratagem')
                rearm=rearm+1
            end
        end
        offset=finish
    end
    assert(offset==#source and #expected==149 and rearm==10,'incomplete_stratagem_table')
    assert(at[REINFORCEMENT] and u32(source,at[REINFORCEMENT]+4)==REINFORCEMENT_ID,'target_missing')
    assert(api.read_module(game+SETTINGS_SLOT,8)==ptr_bytes,'settings_pointer_changed')
    assert(api.read_blob(buffer,SETTINGS_SIZE)==source,'settings_changed')
    return {ptr_bytes=ptr_bytes,buffer=buffer,source=source,at=at}
end

local function apply(choice)
    state.attempts=state.attempts+1
    local ctx=prepare()
    -- A replaced table is a fresh copy; the old memory is never written again.
    if owned and owned.ptr_bytes~=ctx.ptr_bytes then carried,owned=owned.value,nil;state.applied=nil end
    local base=ctx.at[REINFORCEMENT]
    local record=ctx.source:sub(base+1,base+RECORD)
    local target=ctx.buffer+base+FIELD
    local current=u32(record,FIELD)
    local original=with_field(record,0)
    if owned then
        assert(owned.address==target and owned.original==original,'reinforcement_record_changed')
    end
    local selected=ctx.at[choice.type]
    assert(selected and u32(ctx.source,selected+4)==choice.id
        and u32(ctx.source,selected+FIELD)==0,'selected_identity_mismatch')
    if current==choice.type then
        -- Our value, possibly carried into a replacement table: own it so it is watched
        -- and restored like a fresh write.
        if not owned then
            owned={ptr_bytes=ctx.ptr_bytes,address=target,original=original,value=current}
            carried=nil
        end
        state.applied=choice.key
        return 'ALREADY_APPLIED '..choice.key
    end
    local region=assert(api.query(target),'target_region_unavailable')
    assert(region.kind==0x20000 and region.protection==4,'target_not_private_writable')
    assert(api.read_module(game+SETTINGS_SLOT,8)==ctx.ptr_bytes,'settings_pointer_changed')
    assert(api.read(target-FIELD,RECORD)==record,'settings_changed')
    -- One 4-byte write replaces the previous choice, so at most one free stratagem exists.
    local written,details=api.write(target,le32(choice.type))
    local after=api.read(target-FIELD,RECORD)
    if written and after==with_field(original,choice.type) then
        owned={ptr_bytes=ctx.ptr_bytes,address=target,original=original,value=choice.type}
        carried=nil
        state.writes=state.writes+1
        state.applied=choice.key
        return 'APPLIED_READBACK_VERIFIED '..choice.key
    end
    if after==original then
        owned=nil;state.applied=nil
    elseif after~=record then
        owned=nil;state.applied=nil
        error('write_state_unknown '..tostring(details),0)
    end
    error('write_failed '..tostring(details),0)
end

-- Clears the field only while the table, record and value still match this addon's write.
local function restore(label)
    if not owned or not api then return end
    local mine=owned
    owned=nil;state.applied=nil
    local ok,err=pcall(function()
        assert(api.read_module(game+SETTINGS_SLOT,8)==mine.ptr_bytes,'settings_pointer_changed')
        assert(api.read(mine.address-FIELD,RECORD)==with_field(mine.original,mine.value),'value_not_ours')
        local written=api.write(mine.address,le32(0))
        assert(written and api.read(mine.address-FIELD,RECORD)==mine.original,'restore_readback_failed')
    end)
    if ok then
        state.restores=state.restores+1
        note('RESTORED_'..label)
    else
        note('RESTORE_SKIPPED_'..label..' '..reason(err))
    end
end

local function queue(key,delay)
    pending=by_key[key]
    pending_since=ticks
    pending_next=ticks+delay
end

-- Returns immediately; the write happens on the next update callback after the full
-- table validation.
function state.select(key)
    if not by_key[key] then return false,'unknown_choice' end
    if halted then return false,'halted '..halted end
    state.selected=key
    queue(key,1)
    sync_menu()
    return true,'QUEUED'
end

local function halt(why)
    halted=why
    pending=nil
    state.hint=HINTS[why]
    note('HALTED '..why)
end

-- The table can be reallocated or rebuilt between missions. Only the pointer and the
-- 4-byte field are read here; a changed table is revalidated in full before any write.
-- A read that fails proves nothing, so it is retried at the next watch instead of
-- giving up ownership.
local function watch()
    local ptr_bytes=api.read_module(game+SETTINGS_SLOT,8)
    if ptr_bytes==nil then return end
    if ptr_bytes~=owned.ptr_bytes then
        carried,owned=owned.value,nil;state.applied=nil
        queue(state.selected,RETRY_TICKS)
        note('TABLE_REPLACED_REAPPLY_QUEUED')
        return
    end
    local field=api.read(owned.address,4)
    if field==nil or field==le32(owned.value) then return end
    owned=nil;state.applied=nil
    if field==le32(0) then
        queue(state.selected,1)
        note('FIELD_RESET_REAPPLY_QUEUED')
    else
        halt('foreign_write_detected')
    end
end

-- Mod Options Menu ------------------------------------------------------------
-- ModOptionsMenu (mods/cowboybingus/mod_options_menu v1.0.1, api 1) keeps the player's
-- edits pending until APPLY, then, in registration order, stores each changed value and
-- calls its on_change(value,id) from its own update wrapper on the game's Lua thread.
-- BSL does not order addons from different authors, so the menu may appear after this
-- entry; it is looked up on each update until MENU_WAIT_TICKS.
-- A row holds at most 16 choices, so a category row picks one group and each group has
-- its own row. Only the current category's row is unlocked; the others show LOCKED
-- (value 1), and an edit there is refused. The menu has no way to grey a row out.
local MENU_MOD='SUZUKA EXTRA SLOT'
local CATEGORY_ID,KEEP_ID='suzuka_extra_slot.category','suzuka_extra_slot.keep_choice'
local MENU_WAIT_TICKS,MENU_UI_CHECK_TICKS=1200,600
local menu_rows=__MENU_GROUPS__
local row_by_id,place,last_in_row={},{},{} -- place[key]={row,value,category}
for category,row in ipairs(menu_rows) do
    row_by_id[row.id]=row
    for i,key in ipairs(row.keys) do place[key]={row=row,value=i+1,category=category} end
end
last_in_row[place[initial_key].row]=initial_key
local menu,registered_rows

-- Shows the current choice: its category, its row, and LOCKED in every other row. set()
-- does not call on_change, so this never feeds back into menu_changed.
local function show_selected()
    if not menu then return end
    local current=place[state.selected]
    pcall(menu.set,CATEGORY_ID,current.category)
    for _,row in ipairs(menu_rows) do
        if registered_rows[row] then pcall(menu.set,row.id,current.row==row and current.value or 1) end
    end
end

local function choose(key)
    local ok,why=state.select(key)
    if ok then last_in_row[place[key].row]=key end
    return ok,why
end

local function menu_changed(value,id)
    local ok,why,key
    if id==CATEGORY_ID then
        -- A new category switches at once to the choice last used in it (else its first),
        -- so the menu always shows what is applied.
        local row=type(value)=='number' and menu_rows[value]
        if not row then
            why='invalid_menu_value'
        elseif row==place[state.selected].row then
            why='category_unchanged'
        else
            key=last_in_row[row] or row.keys[1]
            ok,why=choose(key)
        end
    else
        local row=row_by_id[id]
        key=row and type(value)=='number' and row.keys[value-1]
        if not row then
            why='unknown_menu_row'
        elseif row~=place[state.selected].row then
            key,why=nil,'row_locked'
        elseif not key then
            why=value==1 and 'locked_entry' or 'invalid_menu_value'
        else
            ok,why=choose(key)
        end
    end
    show_selected()
    if ok then return event('MENU_SELECTED '..key) end
    event('MENU_REFUSED '..tostring(why))
end

local function register_menu(candidate)
    if type(candidate)~='table' or candidate.api~=1 or type(candidate.register_option)~='function'
        or type(candidate.get)~='function' or type(candidate.set)~='function'
        or type(candidate.on_change)~='function' then
        return 'INCOMPATIBLE'
    end
    local initial=place[initial_key]
    local categories={}
    for i,row in ipairs(menu_rows) do categories[i]=row.category end
    local ok,why=candidate.register_option(CATEGORY_ID,{type='choice',mod=MENU_MOD,
        label='Free extra stratagem: category',choices=categories,default=initial.category,
        description='You get ONE free extra mission stratagem, for you only and outside your four '
            ..'slots. Pick its category here, then the stratagem in that category\'s row; the other '
            ..'rows stay LOCKED. Change it on the ship before deploying.'})
    -- Without the category row the other rows cannot be unlocked, so none are offered.
    if not ok then return 'REGISTER_FAILED '..CATEGORY_ID..' '..tostring(why) end
    candidate.on_change(CATEGORY_ID,menu_changed)
    menu,registered_rows=candidate,{}
    sync_menu=function() pcall(show_selected) end
    -- A row the menu refuses is skipped; rows already shown must still work, because
    -- the menu has no way to remove them again.
    local failure
    for _,row in ipairs(menu_rows) do
        local names={'LOCKED'}
        for i,key in ipairs(row.keys) do names[i+1]=by_key[key].menu end
        local row_ok,row_why=candidate.register_option(row.id,{type='choice',mod=MENU_MOD,
            label=row.label,choices=names,default=initial.row==row and initial.value or 1,
            description='Unlocked only while '..row.category..' is the category above. '
                ..'This replaces your one free extra stratagem; it does not add another.'})
        if row_ok then
            registered_rows[row]=true
            candidate.on_change(row.id,menu_changed)
        else
            failure=failure or row.id..' '..tostring(row_why)
        end
    end
    local keep_ok,keep_why=candidate.register_option(KEEP_ID,{type='toggle',mod=MENU_MOD,gap=true,
        label='Keep menu choice after restart',default=false,
        description='Off: every game start uses the choice made in HD2 Arsenal. '
            ..'On: the last applied menu choice is used instead.'})
    if not keep_ok then failure=failure or KEEP_ID..' '..tostring(keep_why) end
    -- The saved category picks the row; a row without a saved value reports its default.
    local saved_row=menu_rows[candidate.get(CATEGORY_ID)]
    local saved=saved_row and registered_rows[saved_row]
        and saved_row.keys[(tonumber(candidate.get(saved_row.id)) or 1)-1]
    if keep_ok and candidate.get(KEEP_ID)==true and saved and saved~=state.selected and not halted then
        state.selected=saved
        last_in_row[saved_row]=saved
        if pending then pending=by_key[saved] else state.select(saved) end
    end
    -- Without the keep toggle the menu starts from the HD2 Arsenal choice.
    show_selected()
    return failure and 'PARTIAL '..failure or 'REGISTERED'
end

-- The menu is offered only on the supported game build, so a game update does not leave
-- rows that refuse every choice.
local function find_menu()
    local candidate=rawget(_G,'ModOptionsMenu')
    if candidate==nil and ticks<MENU_WAIT_TICKS then return end
    if candidate==nil then
        state.menu='UNAVAILABLE'
    else
        local game_ok,err=pcall(check_game)
        local why=not game_ok and reason(err)
        if why and TRANSIENT[why] and ticks<MENU_WAIT_TICKS then return end
        if why then
            state.menu='DISABLED '..why
            state.hint=state.hint or HINTS[why]
        else
            local ok,result=pcall(register_menu,candidate)
            state.menu=ok and result or 'REGISTER_FAILED '..reason(result)
        end
    end
    event('MENU_'..state.menu)
end

-- Mod Options Menu turns its own UI off on a game build it does not support; record that
-- once so a missing MODS tab can be told apart from a registration problem.
local function check_menu_ui()
    local ok,ready=pcall(menu.ready)
    state.menu_ui=not ok and 'UNKNOWN' or ready and 'READY' or 'NOT_READY'
    event('MENU_UI_'..state.menu_ui)
end

local function step()
    if state.menu=='WAITING' then find_menu() end
    if menu and not state.menu_ui and ticks>=MENU_UI_CHECK_TICKS then check_menu_ui() end
    if halted then return end
    if pending and ticks>=pending_next then
        local choice=pending
        local ok,result=pcall(apply,choice)
        if ok then
            if pending==choice then pending=nil end
            note(result)
            return
        end
        local why=reason(result)
        if not TRANSIENT[why] then return halt(why) end
        -- A table that is still loading or moving is only read, never written, so the
        -- choice keeps waiting: often at first, then every WATCH_TICKS.
        if ticks-pending_since<GIVE_UP_TICKS then
            pending_next=ticks+RETRY_TICKS
            state.status='WAITING '..why
        else
            pending_next=ticks+WATCH_TICKS
            if state.status~='WAITING_SLOW '..why then note('WAITING_SLOW '..why) end
        end
    elseif owned and not pending and ticks%WATCH_TICKS==0 then
        watch()
    end
end

state.selected=initial_key
queue(initial_key,RETRY_TICKS)
if rawget(_G,'ModOptionsMenu')~=nil then find_menu() end

local previous_update=rawget(_G,'update')
local function pack(...) return {n=select('#',...),...} end
if type(previous_update)=='function' then
    rawset(_G,'update',function(...)
        local result=pack(previous_update(...))
        ticks=ticks+1
        local ok,err=pcall(step)
        if not ok then pcall(halt,'internal '..reason(err)) end
        return unpack(result,1,result.n)
    end)
else
    halted='no_update_callback'
    note('HALTED no_update_callback')
end

local previous_shutdown=rawget(_G,'shutdown')
rawset(_G,'shutdown',function(...)
    pcall(restore,'SHUTDOWN')
    if type(previous_shutdown)=='function' then return previous_shutdown(...) end
end)

if not halted then note('WAITING') end
