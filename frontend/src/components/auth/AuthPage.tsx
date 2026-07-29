import { useState, type FormEvent, type ReactNode } from "react";
import { Flask } from "@phosphor-icons/react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/context/AuthContext";
import { useToast } from "@/context/ToastContext";
import { register as apiRegister } from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = "login" | "signup";

export function AuthPage() {
  const [tab, setTab] = useState<Tab>("login");

  return (
    <div className="relative min-h-[100dvh] overflow-hidden bg-zinc-950">
      <div className="pointer-events-none absolute inset-0" aria-hidden>
        <div className="absolute left-[6%] top-[-12%] h-[520px] w-[720px] rounded-full bg-accent/[0.07] blur-[140px]" />
        <div className="absolute bottom-[-20%] right-[4%] h-[420px] w-[520px] rounded-full bg-accent/[0.03] blur-[150px]" />
      </div>
      <div className="grain" aria-hidden />

      {/* Editorial split: type on the left, the form as a machined panel right. */}
      <div className="relative mx-auto grid min-h-[100dvh] max-w-[1400px] items-center gap-16 px-6 py-16 lg:grid-cols-[1.05fr_0.95fr] lg:px-16">
        <section className="animate-fade-up">
          <div className="mb-11 flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-xl border border-white/[0.09] bg-white/[0.04] shadow-[inset_0_1px_0_rgba(255,255,255,0.1)]">
              <Flask className="h-4 w-4 text-accent" />
            </div>
            <span className="text-[15px] tracking-tight text-white">ResearchRAG</span>
          </div>

          <span className="eyebrow inline-block rounded-full border border-white/[0.08] bg-white/[0.04] px-3 py-1.5">
            Grounded retrieval
          </span>

          <h1 className="mt-6 max-w-[18ch] text-[clamp(2.5rem,5vw,4.5rem)] font-medium leading-[0.96] tracking-[-0.045em] text-white [text-wrap:balance]">
            Ask your library the way you'd ask a colleague.
          </h1>

          <p className="mt-6 max-w-[44ch] text-[17px] leading-[1.62] text-zinc-400 [text-wrap:pretty]">
            Pull papers from OpenAlex, drop in your own PDFs, and get answers that cite the exact
            passage they came from. Nothing leaves your machine.
          </p>

          <dl className="mt-14 grid max-w-[520px] grid-cols-3 gap-px overflow-hidden rounded-[18px] border border-white/[0.07] bg-white/[0.07]">
            <Stat value="OpenAlex" label="paper source" />
            <Stat value="Chroma" label="vector store" />
            <Stat value="local" label="storage" />
          </dl>
        </section>

        <section className="bezel animate-fade-up shadow-[0_40px_90px_-40px_rgba(0,0,0,0.9)] lg:max-w-[480px] lg:justify-self-end">
          <div className="bezel-core p-8 sm:p-9">
            <div className="grid grid-cols-2 gap-1 rounded-2xl border border-white/[0.06] bg-white/[0.03] p-1">
              <TabButton active={tab === "login"} onClick={() => setTab("login")}>
                Sign in
              </TabButton>
              <TabButton active={tab === "signup"} onClick={() => setTab("signup")}>
                Create account
              </TabButton>
            </div>

            <div className="mt-7">
              {tab === "login" ? <LoginForm /> : <SignupForm onDone={() => setTab("login")} />}
            </div>

            <p className="mt-6 text-[12px] leading-relaxed text-subtle">
              Credentials and vectors are stored locally. Passwords are never transmitted.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="bg-zinc-950 px-5 py-5">
      <dd className="num text-[19px] tracking-tight text-white">{value}</dd>
      <dt className="mt-1.5 text-[11px] uppercase tracking-[0.14em] text-subtle">{label}</dt>
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-[11px] py-3 text-[13.5px] tracking-tight transition-all duration-[500ms] ease-smooth",
        active
          ? "bg-zinc-100 text-zinc-950 shadow-[0_6px_20px_-10px_rgba(0,0,0,0.9)]"
          : "text-zinc-400 hover:text-zinc-200",
      )}
    >
      {children}
    </button>
  );
}

function LoginForm() {
  const { login } = useAuth();
  const toast = useToast();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      toast.error("Enter your username and password first.");
      return;
    }
    setLoading(true);
    try {
      // Throws on bad credentials; on success the token pair is stored and the
      // auth subscription swaps this screen for the workspace.
      await login(username, password);
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <Input
        label="Username"
        placeholder="your_username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        autoComplete="username"
      />
      <Input
        label="Password"
        type="password"
        placeholder="••••••••"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        autoComplete="current-password"
      />
      <Button type="submit" variant="primary" fullWidth loading={loading}>
        Open workspace
      </Button>
    </form>
  );
}

function SignupForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      toast.error("Username and password are required.");
      return;
    }
    if (password !== confirm) {
      toast.error("Password and confirmation do not match.");
      return;
    }
    setLoading(true);
    try {
      const res = await apiRegister(username, displayName, password);
      if (res.success) {
        toast.success(`${res.message} You can now log in.`);
        onDone();
      } else {
        toast.error(res.message);
      }
    } catch (err) {
      toast.error((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <Input
        label="Username"
        placeholder="min. 3 chars — letters/numbers/_"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
      />
      <Input
        label="Display name (optional)"
        placeholder="Name shown in the app"
        value={displayName}
        onChange={(e) => setDisplayName(e.target.value)}
      />
      <Input
        label="Password"
        type="password"
        placeholder="min. 6 chars"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <Input
        label="Confirm password"
        type="password"
        placeholder="Repeat password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
      />
      <Button type="submit" variant="primary" fullWidth loading={loading}>
        Create account
      </Button>
    </form>
  );
}
