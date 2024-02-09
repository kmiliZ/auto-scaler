function get_average_response_time:
    response_times = []
    for monitor_time seconds:
        try:
            Set startRequestTime to currentTime
            Send GET request to web service
            Set endRequestTime to currentTime
            append (endRequestTime - startRequestTime) to response_times
        catch TimeoutException:
            return monitor_time
    else:
        return sum(response_times)/len(response_times)
   
function perform_scaling:
    average_response_time = get_average_response_time()
    current_replicas = service.get_current_replicas()
    new_replicas = current_replicas
    scale = 0
    if average_response_time >= scale_up_threshold:
        if current_replicas < max_replicas:
            scale = average_response_time / scale_up_threshold
            new_replicas = min(current_replicas + scale, max_replicas)
            service.scale(new_replicas)
            print "Scaled up service to new_replicas replicas."
        else:
            print "Reached max replicas, can't scale up."

    elif average_response_time <= scale_down_threshold:
        if current_replicas > min_replicas:
            scale = -(average_response_time / scale_down_threshold)
            new_replicas = max(current_replicas + scale, min_replicas)
            service.scale(new_replicas)
            print "Scaled down service to new_replicas replicas."
        else:
            print "Reached min replicas, can't scale down."
    else:
        print "No scaling performed. Response time within threshold.