// Login page placeholder (route group "(auth)").
// Wire to a real auth service (e.g. Supabase Auth) in src/services/ later.
export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center">
      <form className="flex w-full max-w-sm flex-col gap-4">
        <h1 className="text-2xl font-semibold">Sign in</h1>
        <input
          type="email"
          placeholder="Email"
          className="rounded border px-3 py-2"
        />
        <input
          type="password"
          placeholder="Password"
          className="rounded border px-3 py-2"
        />
        <button type="submit" className="rounded bg-black py-2 text-white">
          Continue
        </button>
      </form>
    </main>
  );
}
