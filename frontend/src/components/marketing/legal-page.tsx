// Shared layout family for the legal pages (Sheet 2A screens 04/05):
// title + "Last updated" placeholder, table of contents on the left,
// long-form reading column on the right. Legal text is owner-supplied,
// so section bodies render clearly-marked placeholder content.
import { LegalToc } from "@/components/marketing/legal-toc";
import { UnavailableNote } from "@/components/marketing/unavailable-note";
import type { LegalSection } from "@/lib/marketing";

interface LegalPageProps {
  title: string;
  sections: LegalSection[];
  /** Placeholder intro shown under the title. */
  lastUpdatedLabel?: string;
  /** Draft notice text (amber, per the design reference). */
  draftNotice: string;
}

// Skeleton bar widths (percentage) mimic the design reference's
// placeholder paragraphs: two wide lines and one shorter line per section.
const SKELETON_ROWS = ["100%", "92%", "55%"];

export function LegalPage({
  title,
  sections,
  lastUpdatedLabel = "[placeholder]",
  draftNotice,
}: LegalPageProps) {
  return (
    <div className="mx-auto max-w-6xl px-4 pb-16 pt-12 sm:px-6">
      <header>
        <h1 className="font-display text-4xl font-semibold text-off-white">{title}</h1>
        <p className="mt-2 font-mono text-xs text-muted">
          Last updated: <span data-testid="legal-last-updated">{lastUpdatedLabel}</span>
        </p>
      </header>

      <div className="mt-10 grid gap-10 lg:grid-cols-[260px_1fr]">
        <aside className="lg:sticky lg:top-24 lg:self-start">
          <LegalToc sections={sections} />
        </aside>

        <div className="flex flex-col gap-10">
          {sections.map((section, index) => (
            <section key={section.id} id={section.id} className="scroll-mt-24">
              <h2 className="font-display text-xl font-semibold text-off-white">
                {index + 1}. {section.title}
              </h2>
              {/* Owner-supplied placeholder body: skeleton bars per the
                  design reference until legal copy is provided. */}
              <div className="mt-4 flex flex-col gap-2.5" aria-hidden="true">
                {SKELETON_ROWS.map((width, rowIndex) => (
                  <div
                    key={rowIndex}
                    className="h-2.5 rounded-full bg-graphite"
                    style={{ width }}
                  />
                ))}
              </div>
              <p className="sr-only">{section.title}: content pending owner/legal review.</p>
            </section>
          ))}

          <UnavailableNote>{draftNotice}</UnavailableNote>
        </div>
      </div>
    </div>
  );
}
