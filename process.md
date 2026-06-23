I know you took the action item to draft a release process, and I also know your plate is pretty full right now.

I’ve been thinking about our delivery headaches and jotted down a lightweight framework that I think could help us get to predictable, quality releases every two weeks. I’ve used a similar setup in the past to help teams get out of this kind of delivery rut, and it worked well.

The main idea is that shipping every two weeks does not mean every piece of work fits neatly into a two-week window. It means work needs to be phased, visible, and managed in a way that lets us reliably ship quality on that cadence, even when larger efforts span multiple cycles.

None of this is especially novel, and a lot of it is probably obvious at a high level. We are already doing most of this in some form today. I’m mostly spelling it out so the expectations are explicit, everyone is operating from the same assumptions, and we add a bit more structure and rigor to make our delivery commitments more reliable.

This is roughly what I had in mind:

- Filter on deliverability: use something like RICE scoring for incoming work, with heavy emphasis on confidence. If a feature lacks enough product or technical clarity to estimate or execute confidently, it should not enter the delivery track yet. Instead, we create explicit follow-up work to clarify it first.

- Timeline and milestones: use Linear’s roadmap timeline as the shared source of truth for release-bound work. If it is not on the timeline, there should be no delivery expectation around it. Larger efforts can span multiple weeks, but they should be broken into clear milestone phases like Discovery/Spike, Implementation, Docs or Migration, and Validation.

- Cycle planning: use cycles and t-shirt estimates to make developer load and progress visible. That gives us a better way to spread work appropriately and avoid overloading individual engineers.

- Developer-owned visibility: for deadline-bearing work, I think developers should be responsible for keeping their cycles, milestones, tickets, and upcoming availability up to date. That includes accounting for PTO and other capacity constraints. The goal is not extra bureaucracy, it is making coordination and planning possible.

- Process support: Veena, in her TPM role, could help keep the process honest by tracking slippage, surfacing communication gaps, and helping make sure updates happen early enough to adjust. Standups and weekly scrums can provide a regular cadence for surfacing issues early and keeping plans current. More broadly, I think the sprint cadence itself can and should be run primarily by developers and the TPM, with managers joining mainly to stay informed, ask questions, and provide input as needed rather than driving the process directly.

- Shift quality left: redefine “Dev Complete” so work does not move into validation until automated tests are verified locally and in k8s. That should help reduce the pattern of throwing partially validated work over the wall to QA.

I do not think this really slows us down so much as spreads the work out more appropriately over time. Throughput may not change much, but it should help us build trust in our estimates and in our ability to ship quality on a predictable cadence.

If this is helpful, I’d be happy to take a first pass at turning it into a short proposal. If you already have a different direction in mind, no worries at all.
