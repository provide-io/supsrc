# 🏗️ Supsrc Responsive UI Architecture Design

## Executive Summary

This document outlines architectural options for ensuring Supsrc's Terminal User Interface (TUI) remains responsive while handling potentially blocking operations like Git commands, file system monitoring, and future features like pytest integration.

## Current State Analysis

### What We Have Now
- **Async event loop** with `asyncio` for concurrent operations
- **Event queue system** for file system events
- **Textual framework** for TUI rendering
- **Synchronous Git operations** via pygit2 (blocking)
- **Single process** architecture

### Performance Bottlenecks
1. **Git operations block** - pygit2 doesn't release Python's GIL
2. **Large repository scans** - Initial discovery can be slow
3. **Commit history fetching** - Can block UI when viewing details
4. **Future pytest integration** - Will need to manage long-running processes

## Architecture Options

### Option 1: Enhanced Async with Thread Pool Executor

#### Overview
Maintain the current single-process architecture but offload blocking operations to thread pools.

#### Implementation
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

class EnhancedOrchestrator:
    def __init__(self):
        # Separate pools for different operation types
        self.git_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="git")
        self.io_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="io")
        self.cpu_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="cpu")
    
    async def git_operation_async(self, operation, *args, **kwargs):
        """Run blocking git operation in thread pool."""
        loop = asyncio.get_event_loop()
        func = partial(operation, *args, **kwargs)
        return await loop.run_in_executor(self.git_executor, func)
    
    async def get_commit_history_async(self, repo_path: Path):
        """Non-blocking commit history fetch."""
        return await self.git_operation_async(
            self._get_commit_history_sync,
            repo_path
        )
```

#### Pros
- ✅ Minimal refactoring required
- ✅ Maintains current architecture
- ✅ Good for I/O-bound operations
- ✅ Easy to implement incrementally

#### Cons
- ❌ Still limited by Python's GIL for CPU-bound work
- ❌ Thread pool overhead
- ❌ Harder to scale beyond single machine
- ❌ Potential thread safety issues with pygit2

### Option 2: Multiprocessing with Shared Memory

#### Overview
Use separate processes for heavy operations with shared memory for state.

#### Implementation
```python
import multiprocessing as mp
from multiprocessing import shared_memory
import pickle

class MultiprocessOrchestrator:
    def __init__(self):
        self.manager = mp.Manager()
        self.repo_states = self.manager.dict()
        self.git_pool = mp.Pool(processes=4)
        
    async def git_operation_multi(self, operation, repo_id, *args):
        """Run git operation in separate process."""
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        
        def callback(result):
            loop.call_soon_threadsafe(future.set_result, result)
        
        self.git_pool.apply_async(
            operation, 
            args=(repo_id, *args),
            callback=callback
        )
        
        return await future
```

#### Pros
- ✅ True parallelism (bypasses GIL)
- ✅ Better CPU utilization
- ✅ Process isolation prevents crashes affecting UI

#### Cons
- ❌ Complex state synchronization
- ❌ Higher memory overhead
- ❌ Serialization costs for IPC
- ❌ Platform-specific quirks

### Option 3: Client-Server Architecture (Recommended for Future)

#### Overview
Split into separate TUI client and background server communicating via RPC.

#### Architecture Diagram
```
┌─────────────────────────────────────────────────────────────┐
│                         TUI Client                          │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │   Textual   │  │  UI State    │  │   RPC Client    │  │
│  │   Widgets   │  │  Management  │  │  (gRPC/Unix)    │  │
│  └─────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────────────┬───────────────────────────────┘
                              │ Protocol Buffers
                              │ or MessagePack
┌─────────────────────────────┴───────────────────────────────┐
│                      Supsrc Server                          │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │   Monitor   │  │     Git      │  │   Test Runner   │  │
│  │   Service   │  │  Operations  │  │    (Future)     │  │
│  └─────────────┘  └──────────────┘  └─────────────────┘  │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              State Management & Events               │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

#### Implementation Using pyvider-rpcplugin
```python
# server.py
from pyvider_rpcplugin import Server, Service
import grpc

class SupsrcService(Service):
    async def GetRepositoryStates(self, request, context):
        states = await self.orchestrator.get_all_states()
        return RepositoryStatesResponse(states=states)
    
    async def StreamEvents(self, request, context):
        async for event in self.orchestrator.event_stream():
            yield Event(
                repo_id=event.repo_id,
                type=event.type,
                data=event.data
            )

# client.py
class SupsrcTUIClient:
    def __init__(self, server_address):
        self.channel = grpc.aio.insecure_channel(server_address)
        self.stub = SupsrcServiceStub(self.channel)
        
    async def subscribe_to_events(self):
        async for event in self.stub.StreamEvents(Empty()):
            self.update_ui(event)
```

#### Pros
- ✅ Complete UI/backend separation
- ✅ TUI can reconnect after crashes
- ✅ Scalable to remote operations
- ✅ Multiple clients possible
- ✅ Best performance isolation

#### Cons
- ❌ Major refactoring required
- ❌ More complex deployment
- ❌ Network/IPC overhead
- ❌ Need to handle connection failures

### Option 4: Hybrid Progressive Architecture (Recommended Path)

#### Overview
Start with thread pools, progressively migrate to client-server as features demand it.

#### Phase 1: Thread Pool Enhancement (Immediate)
```python
class ResponsiveOrchestrator:
    def __init__(self):
        self.git_executor = ThreadPoolExecutor(max_workers=4)
        self._operation_cache = TTLCache(maxsize=100, ttl=300)
        
    async def cached_git_operation(self, cache_key, operation, *args):
        """Cache expensive git operations."""
        if cache_key in self._operation_cache:
            return self._operation_cache[cache_key]
            
        result = await self.git_operation_async(operation, *args)
        self._operation_cache[cache_key] = result
        return result
```

#### Phase 2: Message Priority System
```python
from enum import IntEnum
from queue import PriorityQueue

class MessagePriority(IntEnum):
    UI_INTERACTION = 1    # Keyboard events, user actions
    STATE_UPDATE = 2      # Repository state changes
    BACKGROUND_TASK = 3   # Git operations, scans
    LOG_MESSAGE = 4       # Lowest priority

class PriorityEventQueue:
    def __init__(self):
        self._queue = PriorityQueue()
        
    async def put(self, priority: MessagePriority, item):
        await self._queue.put((priority, time.time(), item))
        
    async def get(self):
        _, _, item = await self._queue.get()
        return item
```

#### Phase 3: Debouncing and Batching
```python
class DebouncedUpdater:
    def __init__(self, update_delay=0.1):
        self.update_delay = update_delay
        self.pending_updates = {}
        self._update_tasks = {}
        
    async def schedule_update(self, repo_id: str, update_func):
        # Cancel existing scheduled update
        if repo_id in self._update_tasks:
            self._update_tasks[repo_id].cancel()
            
        # Schedule new update
        self._update_tasks[repo_id] = asyncio.create_task(
            self._delayed_update(repo_id, update_func)
        )
        
    async def _delayed_update(self, repo_id: str, update_func):
        await asyncio.sleep(self.update_delay)
        await update_func()
        self._update_tasks.pop(repo_id, None)
```

#### Phase 4: Server Migration (When Adding pytest/Complex Features)
- Extract core logic into service classes
- Add RPC layer using pyvider-rpcplugin
- Keep TUI as thin client
- Implement reconnection logic

## Performance Optimization Strategies

### 1. Virtual Scrolling for Large Repository Lists
```python
class VirtualDataTable(DataTable):
    def __init__(self, visible_rows=50):
        super().__init__()
        self.visible_rows = visible_rows
        self.data_source = []
        self.viewport_start = 0
        
    def update_viewport(self, scroll_position):
        self.viewport_start = scroll_position
        self.refresh_visible_rows()
        
    def refresh_visible_rows(self):
        visible = self.data_source[
            self.viewport_start:self.viewport_start + self.visible_rows
        ]
        self.update_display(visible)
```

### 2. Lazy Loading with Prefetching
```python
class LazyRepositoryDetails:
    def __init__(self, repo_id: str):
        self.repo_id = repo_id
        self._commit_history = None
        self._prefetch_task = None
        
    def start_prefetch(self):
        """Start loading in background when repo is highlighted."""
        if not self._prefetch_task:
            self._prefetch_task = asyncio.create_task(
                self._load_commit_history()
            )
            
    async def get_commit_history(self):
        """Get history, waiting if still loading."""
        if self._commit_history is None:
            if self._prefetch_task:
                await self._prefetch_task
            else:
                await self._load_commit_history()
        return self._commit_history
```

### 3. Intelligent Caching
```python
from functools import lru_cache
from cachetools import TTLCache

class SmartCache:
    def __init__(self):
        # Different caches for different data types
        self.commit_cache = TTLCache(maxsize=1000, ttl=300)  # 5 min
        self.status_cache = TTLCache(maxsize=100, ttl=10)    # 10 sec
        self.static_cache = {}  # Never expires
        
    async def get_or_compute(self, cache_type, key, compute_func):
        cache = getattr(self, f"{cache_type}_cache")
        if key in cache:
            return cache[key]
            
        value = await compute_func()
        cache[key] = value
        return value
```

## Implementation Recommendations

### Immediate Actions (Phase 1)
1. **Add ThreadPoolExecutor** for git operations
2. **Implement operation caching** for expensive calls
3. **Add message priorities** to event queue
4. **Implement debouncing** for rapid file changes

### Medium Term (Phase 2)
1. **Profile performance** bottlenecks
2. **Add virtual scrolling** if repo lists get large
3. **Implement lazy loading** for detail views
4. **Add progress indicators** for long operations

### Long Term (Phase 3)
1. **Design RPC protocol** for client-server split
2. **Extract service layer** from orchestrator
3. **Implement server** with pyvider-rpcplugin
4. **Migrate TUI** to thin client model

## Monitoring and Metrics

### Performance Metrics to Track
```python
class PerformanceMonitor:
    def __init__(self):
        self.metrics = {
            'ui_response_time': [],      # Time to process UI events
            'git_operation_time': [],     # Git operation durations
            'event_queue_size': [],       # Queue depth over time
            'frame_render_time': [],      # TUI frame render duration
        }
        
    @contextmanager
    def measure(self, metric_name):
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.metrics[metric_name].append(duration)
            
            # Log if exceeds threshold
            if duration > self.get_threshold(metric_name):
                log.warning(f"{metric_name} took {duration:.2f}s")
```

## Conclusion

The recommended approach is the **Hybrid Progressive Architecture**:

1. **Start with thread pools** to solve immediate blocking issues
2. **Add performance optimizations** as needed
3. **Migrate to client-server** when adding complex features like pytest integration

This provides immediate benefits while keeping the door open for future architectural improvements.

---

*Document Version: 1.0*  
*Last Updated: 2025-08-09*


# 🏗️🚀📋🔧