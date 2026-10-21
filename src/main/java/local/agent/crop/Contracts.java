package local.agent.crop;

import java.util.List;

/** Shared boundary with the team's backend and downstream recommendation module. */
public final class Contracts {
    private Contracts() {}

    /** Documents and image symptoms are extracted text supplied by upstream modules. */
    public record Input(String crop, String symptoms, String growthStage, String environment,
                        String documentText, String imageSymptoms) {}

    public record SearchQuery(String crop, String query, int topK) {}

    /** Score is the backend's normalized retrieval similarity, not diagnostic probability. */
    public record Evidence(String id, String nutrient, List<String> crops, String text,
                           String sourceUrl, double score) {}

    public record SearchResponse(List<Evidence> matches) {}
    public enum Status { READY, NEED_MORE_INFO, KNOWLEDGE_UNAVAILABLE }

    public record Candidate(String nutrient, double matchScore, List<String> evidenceIds) {}

    /** Public evidence summary only; never request or persist private chain of thought. */
    public record Decision(Status status, List<Candidate> candidates, List<Evidence> evidence,
                           List<String> questions, List<String> nextActions, String summary,
                           String mode, List<String> warnings) {}

    /** Model selects evidence IDs; nutrient names and scores are resolved from trusted evidence. */
    public record ModelDecision(String status, List<String> evidenceIds, List<String> questions) {}
}
