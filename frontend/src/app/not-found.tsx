import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { Wordmark } from "@/components/wordmark";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 px-4 text-center">
      <Wordmark className="text-lg" />
      <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
      <p className="text-sm text-muted-foreground">
        The page you&rsquo;re looking for doesn&rsquo;t exist or has moved.
      </p>
      <Link href="/" className={buttonVariants({ variant: "outline" })}>
        Go home
      </Link>
    </div>
  );
}
