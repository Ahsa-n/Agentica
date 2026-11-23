# SOP: Handling High Memory Usage

## Overview
Procedure for responding to high memory usage alerts on servers.

## Thresholds
- Warning: 85% memory used
- Critical: 95% memory used

## Procedure

### Step 1: Assess the situation
1. Run `get_memory_usage` to get current memory statistics
2. Run `list_top_processes` sorted by memory to identify consumers
3. Check if swap is being used heavily (indicates memory pressure)

### Step 2: Identify the cause
1. Review which processes are consuming the most memory
2. Check if this is expected growth or sudden spike
3. Run `get_process_details` on the top consumers for more info

### Step 3: Immediate response
1. If a single rogue process is consuming memory:
   - Document the process name and PID
   - Request service restart if the process is a known service: `restart_service <service_name>`
   - Requires administrator confirmation
2. If memory growth is gradual:
   - Check for memory leaks in application logs
   - Schedule maintenance window for service restart

### Step 4: Verify improvement
1. Run `get_memory_usage` again to confirm memory has decreased
2. Monitor for 15 minutes to ensure stability

### Prevention
- Configure automated alerts at 85% threshold
- Review application memory limits in configuration
- Implement regular memory monitoring in Agentica
