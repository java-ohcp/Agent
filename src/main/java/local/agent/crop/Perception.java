package local.agent.crop;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import static local.agent.crop.Contracts.*;

/** Perception: normalize text, construct the retrieval query, validate returned evidence. */
public final class Perception {
    public record Context(Input input, SearchQuery query, List<Evidence> evidence) {}
    private final KnowledgeSearch search;

    public Perception(KnowledgeSearch search) {
        this.search = java.util.Objects.requireNonNull(search);
    }

    public Context receive(Input input) throws Exception {
        if (input == null) throw new IllegalArgumentException("Input is required");
        var normalized = new Input(clean(input.crop(), 100), clean(input.symptoms(), 4000),
                clean(input.growthStage(), 200), clean(input.environment(), 2000),
                clean(input.documentText(), 6000), clean(input.imageSymptoms(), 2000));
        if ((normalized.symptoms() + normalized.documentText() + normalized.imageSymptoms()).isBlank()) {
            throw new IllegalArgumentException("请提供症状描述或已提取的文档、图片症状文本");
        }
        String queryText = "作物：" + normalized.crop() + "\n症状：" + normalized.symptoms()
                + "\n生育期：" + normalized.growthStage() + "\n环境：" + normalized.environment()
                + "\n文档摘录：" + normalized.documentText() + "\n图片症状：" + normalized.imageSymptoms();
        var query = new SearchQuery(normalized.crop(), queryText, 8);
        List<Evidence> results = search.search(query);
        if (results == null) throw new IllegalStateException("Knowledge service returned null");
        var unique = new LinkedHashMap<String, Evidence>();
        results.stream().filter(e -> valid(e, normalized.crop()))
                .sorted(Comparator.comparingDouble(Evidence::score).reversed())
                .forEach(e -> unique.putIfAbsent(e.id(), e));
        return new Context(normalized, query, unique.values().stream().limit(8).toList());
    }

    private static boolean valid(Evidence e, String crop) {
        return e != null && present(e.id(), 200) && present(e.nutrient(), 100)
                && present(e.text(), 12000) && present(e.sourceUrl(), 2000)
                && Double.isFinite(e.score()) && e.score() >= 0 && e.score() <= 1
                && e.crops() != null && !e.crops().isEmpty()
                && (crop.isBlank() || e.crops().contains(crop) || e.crops().contains("通用"));
    }

    private static boolean present(String value, int max) {
        return value != null && !value.isBlank() && value.length() <= max;
    }

    private static String clean(String value, int max) {
        if (value == null) return "";
        if (value.length() > max) throw new IllegalArgumentException("Input field exceeds " + max + " characters");
        return value.replaceAll("[\\p{Cntrl}&&[^\\n\\t]]", " ").strip();
    }
}
