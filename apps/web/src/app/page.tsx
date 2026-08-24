import Link from "next/link";
import type { CSSProperties } from "react";

import { WaitlistForm } from "./waitlist-form";
import styles from "./landing.module.css";

function ArrowIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={styles.arrowIcon}>
      <path d="M4 10h11M11 5l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function TickIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" className={styles.tickIcon}>
      <path d="m4 10 4 4 8-9" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export default function Home() {
  return (
    <div className={styles.page}>
      <a href="#main-content" className={styles.skipLink}>
        Skip to content
      </a>

      <header className={styles.header}>
        <div className={styles.headerInner}>
          <Link href="/" className={styles.brand} aria-label="Faida home">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/brand/faida-mark.svg" alt="" className={styles.brandMark} />
            <span>faida</span>
          </Link>
          <nav className={styles.nav} aria-label="Primary navigation">
            <a href="#how-it-works">How it works</a>
            <a href="#what-you-get">What you get</a>
          </nav>
          <a href="#waitlist-form" className={styles.headerCta}>
            Join the waitlist
            <ArrowIcon />
          </a>
        </div>
      </header>

      <main id="main-content">
        <section className={styles.hero} aria-labelledby="hero-title">
          <div className={styles.heroCopy}>
            <p className={styles.eyebrow}>
              <span aria-hidden="true" />
              Private pilot for GCC cafeteria operators
            </p>
            <h1 id="hero-title">
              Know the profit margin
              <strong> on every item you sell.</strong>
            </h1>
            <p className={styles.promise}>
              Faida reads the supplier invoices your team already forwards on WhatsApp, pairs
              them with daily sales, and shows which items and branches are helping or hurting
              profit, with every number traceable to its source.
            </p>
            <WaitlistForm />
            <div className={styles.formProof} aria-label="Waitlist details">
              <span>
                <TickIcon /> No card required
              </span>
              <span>
                <TickIcon /> Pilot access first
              </span>
              <span>
                <TickIcon /> One useful email only
              </span>
            </div>
          </div>

          <div className={styles.proofStage} aria-label="Example Faida invoice price alert">
            <div className={styles.proofTopline}>
              <span>One forwarded invoice</span>
              <span>21 Aug · 09:42</span>
            </div>

            <div className={styles.forwardedCard}>
              <div className={styles.documentIcon} aria-hidden="true">
                <span />
                <span />
                <span />
              </div>
              <div>
                <p>IMG_2048.jpg</p>
                <span>Forwarded from Al Quoz</span>
              </div>
              <div className={styles.fileCheck} aria-label="Photo received">
                <TickIcon />
              </div>
            </div>

            <div className={styles.flowTrack} aria-hidden="true">
              <span />
              <i />
              <span />
            </div>

            <div className={styles.alertCard}>
              <div className={styles.alertHeader}>
                <div className={styles.miniBrand}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src="/brand/faida-mark.svg" alt="" />
                  <span>faida</span>
                </div>
                <span className={styles.verifiedTag}>
                  <TickIcon /> Checked
                </span>
              </div>
              <p className={styles.supplier}>Al Madina Foodstuff</p>
              <p className={styles.invoiceMeta}>Invoice #10482 · AED 716.89</p>
              <div className={styles.priceMove}>
                <div>
                  <span>PRICE MOVE</span>
                  <strong>Milk powder is up AED 4.00</strong>
                </div>
                <b>+7.9%</b>
              </div>
              <p className={styles.sourceNote}>Compared with the last confirmed invoice</p>
            </div>

            <div className={styles.proofFooter}>
              <span>Photo</span>
              <i aria-hidden="true" />
              <span>Checked fields</span>
              <i aria-hidden="true" />
              <strong>Visible impact</strong>
            </div>
          </div>
        </section>

        <div className={styles.truthStrip} aria-label="Faida principles">
          <p>No new workflow.</p>
          <p>No unexplained numbers.</p>
          <p>No pretending an estimate is verified profit.</p>
        </div>

        <section id="how-it-works" className={styles.process} aria-labelledby="process-title">
          <div className={styles.sectionLead}>
            <p className={styles.sectionLabel}>The working loop</p>
            <h2 id="process-title">From invoice photo to a decision worth making.</h2>
            <p>
              Faida meets your team where supplier work already happens, then gives owners the
              evidence behind every alert.
            </p>
          </div>

          <ol className={styles.steps}>
            <li>
              <span className={styles.stepNumber}>01</span>
              <div className={styles.stepIcon} aria-hidden="true">
                <svg viewBox="0 0 28 28">
                  <path d="M5 6h18v13H10l-5 4V6Z" fill="none" stroke="currentColor" strokeWidth="1.7" />
                  <path d="m10 13 3 3 6-7" fill="none" stroke="currentColor" strokeWidth="1.7" />
                </svg>
              </div>
              <h3>Forward</h3>
              <p>Send the supplier invoice to one WhatsApp number. No new login or data-entry ritual.</p>
            </li>
            <li>
              <span className={styles.stepNumber}>02</span>
              <div className={styles.stepIcon} aria-hidden="true">
                <svg viewBox="0 0 28 28">
                  <path d="M7 4h14v20H7z" fill="none" stroke="currentColor" strokeWidth="1.7" />
                  <path d="M10 9h8M10 13h8M10 17h5" fill="none" stroke="currentColor" strokeWidth="1.7" />
                </svg>
              </div>
              <h3>Check</h3>
              <p>Faida reads each line, reconciles the arithmetic, and asks when a field needs review.</p>
            </li>
            <li>
              <span className={styles.stepNumber}>03</span>
              <div className={styles.stepIcon} aria-hidden="true">
                <svg viewBox="0 0 28 28">
                  <path d="M5 22V11M12 22V6M19 22V14M4 22h20" fill="none" stroke="currentColor" strokeWidth="1.7" />
                </svg>
              </div>
              <h3>See the impact</h3>
              <p>Item margins, price moves, and branch comparisons appear with a path back to the original invoice.</p>
            </li>
          </ol>
        </section>

        <section id="what-you-get" className={styles.capabilities} aria-labelledby="capabilities-title">
          <div className={styles.sectionLead}>
            <p className={styles.sectionLabel}>What Faida will do</p>
            <h2 id="capabilities-title">The daily questions, answered without another spreadsheet.</h2>
          </div>

          <div className={styles.capabilityGrid}>
            <article className={styles.featurePrimary}>
              <div className={styles.featureIndex}>Item margins</div>
              <h3>See which items earn their place and which quietly lose money.</h3>
              <p>
                Faida builds each item&apos;s true cost from confirmed supplier invoices and sets
                it against what the item sells for, ranked so the quiet losers stand out before
                the month ends.
              </p>
              <div className={styles.priceLedger} aria-label="Example margin per item">
                <div>
                  <span>KARAK</span>
                  <b>61%</b>
                </div>
                <div>
                  <span>SAMOSA</span>
                  <b>44%</b>
                </div>
                <div className={styles.currentPrice}>
                  <span>MANGO JUICE</span>
                  <b>9%</b>
                </div>
              </div>
            </article>

            <article>
              <div className={styles.featureIndex}>Supplier prices</div>
              <h3>Catch the cost moves that eat item margins.</h3>
              <p>
                When an ingredient&apos;s price climbs, every item using it earns less. Faida
                shows what changed, by how much, and against which confirmed invoice.
              </p>
              <div className={styles.priceLedger} aria-label="Example milk powder price history">
                <div>
                  <span>08 AUG</span>
                  <b>AED 50.50</b>
                </div>
                <div>
                  <span>15 AUG</span>
                  <b>AED 50.50</b>
                </div>
                <div className={styles.currentPrice}>
                  <span>21 AUG</span>
                  <b>AED 54.50</b>
                </div>
              </div>
            </article>

            <article>
              <div className={styles.featureIndex}>Branch view</div>
              <h3>Compare every branch on one honest basis.</h3>
              <p>
                See purchases against net sales, supplier movements, and contribution estimates
                with completeness stated beside the number.
              </p>
              <div className={styles.branchBars} aria-hidden="true">
                <span style={{ "--bar": "88%" } as CSSProperties} />
                <span style={{ "--bar": "67%" } as CSSProperties} />
                <span style={{ "--bar": "51%" } as CSSProperties} />
              </div>
            </article>
          </div>
        </section>

        <section className={styles.trustSection} aria-labelledby="trust-title">
          <div>
            <p className={styles.sectionLabel}>Built for trust</p>
            <h2 id="trust-title">The useful part is not magic. It is the proof.</h2>
          </div>
          <div className={styles.trustCopy}>
            <p>
              Faida uses extraction to read a document, then deterministic checks validate the
              numbers. Financial results never come from a generated guess.
            </p>
            <ul>
              <li>Original invoice photos stay attached to the record.</li>
              <li>Wrong or uncertain fields are flagged for review.</li>
              <li>Incomplete data produces an incomplete label, not false precision.</li>
            </ul>
          </div>
        </section>

        <section className={styles.finalCta} aria-labelledby="final-cta-title">
          <div className={styles.finalMark} aria-hidden="true">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/brand/faida-mark.svg" alt="" />
          </div>
          <p className={styles.sectionLabel}>Private pilot</p>
          <h2 id="final-cta-title">Every item. Every branch. Real margins.</h2>
          <p>Join the first GCC cafeteria operators shaping Faida before launch.</p>
          <a href="#waitlist-form" className={styles.finalButton}>
            Join the waitlist
            <ArrowIcon />
          </a>
        </section>
      </main>

      <footer className={styles.footer}>
        <Link href="/" className={styles.footerBrand} aria-label="Faida home">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/brand/faida-mark.svg" alt="" />
          <span>faida</span>
        </Link>
        <p>Profit visibility for GCC cafeterias and multi-branch operators.</p>
        <span>© {new Date().getFullYear()} Faida</span>
      </footer>
    </div>
  );
}
