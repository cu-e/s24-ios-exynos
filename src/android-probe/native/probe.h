#pragma once
#include <atomic>
#include <string>

struct ProbeResult {
    std::string outcome = "fail", error, device;
    unsigned api = 0, driver = 0, vendor = 0, device_id = 0;
    unsigned compared = 0, mismatched = 0;
    bool requires_restart = false;
    double elapsed_ms = 0;
    std::string json() const;
};

ProbeResult run_probe(std::atomic_bool &stop, unsigned deadline_ms = 4000);
