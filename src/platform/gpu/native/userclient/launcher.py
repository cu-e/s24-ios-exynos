#!/usr/bin/env python3
"""In-process finite cancellation wrapper; never creates a process or provider."""
import argparse
import hashlib
import signal
import sys
from pathlib import Path
from types import ModuleType

sys.dont_write_bytecode=True
ADMISSION_SHA="99b6cc21ca41a6b8153e26474466f29ef0443101f274cda1f20815e21c1ea756"


class Cancelled(BaseException):
    pass


def guarded(callback, seconds=600):
    if type(seconds) not in (int,float) or not 0<seconds<=600:
        raise ValueError("Finite whole-phase deadline <=600 seconds required")
    if signal.getitimer(signal.ITIMER_REAL)!=(0.0,0.0):
        raise ValueError("Existing timer authority must not be replaced")
    previous={s:signal.getsignal(s) for s in [signal.SIGALRM,signal.SIGTERM,signal.SIGINT]}
    record={"cancellation":None,"signals":[],"entered":False}
    def stop(number,frame):
        record["signals"].append(number)
        # Repeated TERM/INT/ALRM must not interrupt shared finally cleanup.
        if record["cancellation"] is None:
            record["cancellation"]="deadline" if number==signal.SIGALRM else "signal-"+str(number)
            raise Cancelled(record["cancellation"])
    try:
        for number in previous: signal.signal(number,stop)
        signal.setitimer(signal.ITIMER_REAL,seconds)
        record["entered"]=True
        try:
            record["result"]=callback()
            record["outcome"]="pass"
        except Cancelled:
            record["outcome"]="cancelled"
        return record
    finally:
        # Pending cancellation belongs to the caller once cleanup is complete.
        # Restore every handler/timer while blocked, then restore the exact
        # caller mask last so pending delivery cannot abort partial restoration.
        prior_mask=signal.pthread_sigmask(signal.SIG_BLOCK,set(previous))
        try:
            signal.setitimer(signal.ITIMER_REAL,0)
            for number,handler in previous.items(): signal.signal(number,handler)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK,prior_mask)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan",type=Path,required=True)
    parser.add_argument("--plan-sha256",required=True)
    parser.add_argument("--approval",type=Path,required=True)
    args=parser.parse_args()
    target=Path(__file__).resolve().with_name("admission.py")
    with target.open("rb") as stream: raw=stream.read(1024**2+1)
    if len(raw)>1024**2 or hashlib.sha256(raw).hexdigest()!=ADMISSION_SHA:
        print("GPU admission refused: changed executor source",file=sys.stderr)
        return 2
    admission=ModuleType("gpu_exact_executor");admission.__file__=str(target)
    exec(compile(raw,str(target),"exec"),admission.__dict__)
    # exact plan binds this launcher as well as the executor; admission checks
    # both before policy reservation, output creation or process launch.
    try:
        result=guarded(lambda:admission.execute(args.plan,args.plan_sha256,args.approval))
        print(result)
        return 130 if result["outcome"]=="cancelled" else 0
    except (ValueError,OSError,KeyError,StopIteration) as error:
        print("GPU admission refused: "+str(error),file=sys.stderr)
        return 2


if __name__=="__main__":
    sys.exit(main())
