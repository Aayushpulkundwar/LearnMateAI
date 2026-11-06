"""Validate, summarize, review, and export a versioned JSONL evaluation dataset."""
import argparse
import json
from app.evaluation.review_dataset import adjudicate_claim, append_review, export_csv_report, load_review_dataset, reviewer_agreement, validate_review_dataset


def main(args):
    if args.command == "validate":
        errors = validate_review_dataset(load_review_dataset(args.dataset))
        print(json.dumps({"valid": not errors, "errors": errors}, indent=2)); raise SystemExit(bool(errors))
    if args.command == "agreement": print(json.dumps(reviewer_agreement(load_review_dataset(args.dataset)), indent=2)); return
    if args.command == "review": append_review(args.dataset, record_id=args.id, claim_id=args.claim_id, reviewer_id=args.reviewer, label=args.label, rationale=args.rationale); return
    if args.command == "adjudicate": adjudicate_claim(args.dataset, record_id=args.id, claim_id=args.claim_id, adjudicator_id=args.adjudicator, label=args.label, rationale=args.rationale); return
    if args.command == "export-csv": export_csv_report(json.loads(open(args.report, encoding="utf-8").read()), args.output)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "agreement"):
        item = sub.add_parser(name); item.add_argument("dataset")
    review = sub.add_parser("review"); review.add_argument("dataset"); review.add_argument("--id", required=True); review.add_argument("--claim-id", required=True); review.add_argument("--reviewer", required=True); review.add_argument("--label", choices=("supported", "contradicted", "insufficiently_evidenced"), required=True); review.add_argument("--rationale", required=True)
    adjudicate = sub.add_parser("adjudicate"); adjudicate.add_argument("dataset"); adjudicate.add_argument("--id", required=True); adjudicate.add_argument("--claim-id", required=True); adjudicate.add_argument("--adjudicator", required=True); adjudicate.add_argument("--label", choices=("supported", "contradicted", "insufficiently_evidenced"), required=True); adjudicate.add_argument("--rationale", required=True)
    export = sub.add_parser("export-csv"); export.add_argument("report"); export.add_argument("output")
    return parser.parse_args()


if __name__ == "__main__": main(parse_args())
