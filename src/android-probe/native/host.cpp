#include "probe.h"
#include <iostream>

int main(int argc, char **argv) {
    std::atomic_bool stop{argc > 1 && std::string(argv[1]) == "--cancel"};
    unsigned deadline = argc > 1 && std::string(argv[1]) == "--deadline" ? 1 : 4000;
    auto result = run_probe(stop, deadline);
    std::cout << result.json() << '\n';
    if (stop.load()) return result.outcome == "cancelled" ? 0 : 1;
    if (deadline == 1) return result.outcome != "pass" ? 0 : 1;
    return result.outcome == "pass" && result.compared == 65536 && result.mismatched == 0 ? 0 : 1;
}
