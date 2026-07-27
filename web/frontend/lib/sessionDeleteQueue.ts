import { deleteSession } from "./api/chats";

type FailHandler = (sessionId: string, error: Error) => void;

class SessionDeleteQueue {
  private queue: string[] = [];
  private inFlight = new Set<string>();
  private pending = new Set<string>();
  private maxConcurrent = 1;
  private onFail: FailHandler | null = null;

  setOnFail(handler: FailHandler | null) {
    this.onFail = handler;
  }

  /** Returns false if this session is already queued. */
  enqueue(sessionId: string): boolean {
    if (this.pending.has(sessionId) || this.inFlight.has(sessionId)) {
      return false;
    }
    this.pending.add(sessionId);
    this.queue.push(sessionId);
    this.pump();
    return true;
  }

  has(sessionId: string): boolean {
    return this.pending.has(sessionId) || this.inFlight.has(sessionId);
  }

  private pump() {
    while (this.inFlight.size < this.maxConcurrent && this.queue.length > 0) {
      const id = this.queue.shift();
      if (!id) break;
      this.inFlight.add(id);
      void this.run(id);
    }
  }

  private async run(sessionId: string) {
    try {
      await deleteSession(sessionId);
    } catch (err) {
      this.onFail?.(
        sessionId,
        err instanceof Error ? err : new Error(String(err)),
      );
    } finally {
      this.pending.delete(sessionId);
      this.inFlight.delete(sessionId);
      this.pump();
    }
  }
}

export const sessionDeleteQueue = new SessionDeleteQueue();
