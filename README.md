# Announcements

--------------------------------------------------------------------------------
![SC2 Banner](doc/resources/SC2_Banner.png)
https://spectrumcollaborationchallenge.com

# Phase 3 SC2 CIL Project

This project develops the Spectrum Collaboration Challenge (SC2) CIRN (Collaborative Intelligent Radio Network) Interaction Language. The language is called the SC2 CIL (pronounced “sill”).

## Role of the SC2 CIL

As envisioned in SC2, CIRNs are designed independently. They may not have enough in common at the physical, MAC, or higher layers to exchange information directly over the air. Nevertheless, CIRNs need to work together in order to coexist in shared spectrum. Each CIRN is assumed to contain a gateway that is connected to a Collaboration Network (wired or wireless) over which the CIRNs can exchange IP messages.

The SC2 CIL specifies the contents of Collaboration Network messages sufficiently for CIRNs to carry out communicative acts. The communicative acts supported are those required to jointly manage and share available spectrum resources effectively. This scope is intentionally broad. For example, the CIL may specify information as low level as the wire representation of messages, and as high level as the semantics of a currency used in transactions for spectrum access.

The Collaboration Network may have impairments such as limited bandwidth, high latency or high packet loss. The CIL does not provide a solution for achieving reliable joint outcomes among CIRNs in the presence of Collaboration Network impairments. It is envisioned that distributed algorithms to achieve reliable outcomes (e.g. leader election, voting) can be implemented on top of CIL messages if required.