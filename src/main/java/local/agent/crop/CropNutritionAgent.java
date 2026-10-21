package local.agent.crop;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Objects;
import static local.agent.crop.Contracts.*;

/** Fixed retrieval-first plan, bounded model repair, and evidence validation. No backend server. */
public final class CropNutritionAgent {
    private final Perception perception;
    private final DecisionModel model;
    private final double threshold;

    public CropNutritionAgent(KnowledgeSearch search, DecisionModel model, double threshold) {
        this.perception = new Perception(search);
        this.model = Objects.requireNonNull(model);
        if (!Double.isFinite(threshold) || threshold < 0 || threshold > 1) {
            throw new IllegalArgumentException("threshold must be within [0,1]");
        }
        this.threshold = threshold;
    }

    public Decision analyze(Input input) {
        if (input == null) throw new IllegalArgumentException("Input is required");
        final Perception.Context context;
        try {
            context = perception.receive(input);
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return unavailable();
        } catch (Exception e) {
            return unavailable();
        }
        var eligible = context.evidence().stream().filter(e -> e.score() >= threshold).toList();
        if (eligible.isEmpty() || context.input().crop().isBlank()) {
            return clarify(context.evidence(), "尚无足够的适用证据，请补充信息后再次检索。", List.of());
        }
        // The model never sees weak evidence excluded by the configured retrieval threshold.
        var grounded = new Perception.Context(context.input(), context.query(), eligible);
        for (int attempt = 0; attempt < 2; attempt++) {
            try {
                ModelDecision proposed = model.decide(grounded);
                Decision checked = validate(proposed, eligible);
                if (checked != null) return checked;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            } catch (Exception e) {
                // One bounded retry; never replace missing knowledge with model memory.
            }
        }
        return clarify(eligible, "模型结果未通过证据校验，请补充信息或稍后重试。",
                List.of("MODEL_UNAVAILABLE_OR_INVALID"));
    }

    private Decision validate(ModelDecision proposed, List<Evidence> evidence) {
        if (proposed == null || proposed.evidenceIds() == null || proposed.questions() == null
                || proposed.evidenceIds().size() > 8 || proposed.questions().size() > 5) return null;
        var byId = new LinkedHashMap<String, Evidence>();
        evidence.forEach(e -> byId.put(e.id(), e));
        if (proposed.evidenceIds().stream().anyMatch(id -> !byId.containsKey(id))) return null;
        if (proposed.questions().stream().anyMatch(q -> q == null || q.isBlank() || q.length() > 300)) return null;
        if ("NEED_MORE_INFO".equals(proposed.status())) {
            return new Decision(Status.NEED_MORE_INFO, List.of(), evidence,
                    proposed.questions().isEmpty() ? defaultQuestions() : List.copyOf(proposed.questions()),
                    List.of("补充信息后重新检索"), "证据不足，暂不移交施肥建议模块。", "RAG_MODEL", List.of());
        }
        if (!"READY".equals(proposed.status()) || proposed.evidenceIds().isEmpty()
                || !proposed.questions().isEmpty()) return null;
        var groups = new LinkedHashMap<String, List<Evidence>>();
        proposed.evidenceIds().stream().distinct().map(byId::get)
                .forEach(e -> groups.computeIfAbsent(e.nutrient(), ignored -> new ArrayList<>()).add(e));
        if (groups.size() > 3) return null;
        var candidates = groups.entrySet().stream().map(entry -> new Candidate(entry.getKey(),
                entry.getValue().stream().mapToDouble(Evidence::score).max().orElseThrow(),
                entry.getValue().stream().map(Evidence::id).toList()))
                .sorted(java.util.Comparator.comparingDouble(Candidate::matchScore).reversed()).toList();
        var selected = proposed.evidenceIds().stream().distinct().map(byId::get).toList();
        return new Decision(Status.READY, candidates, selected, List.of(),
                List.of("将候选类型和引用证据交给施肥建议模块", "结合土壤或植株检测复核"),
                "已依据检索证据形成候选结果；匹配分数不是确诊概率。科学施肥，减少盲目投入。",
                "RAG_MODEL", List.of("症状可能与病害、药害或水分胁迫相似，需结合田间情况复核。"));
    }

    private Decision clarify(List<Evidence> evidence, String summary, List<String> warnings) {
        return new Decision(Status.NEED_MORE_INFO, List.of(), evidence, defaultQuestions(),
                List.of("补充信息后重新检索"), summary, "EVIDENCE_GUARD", warnings);
    }

    private static List<String> defaultQuestions() {
        return List.of("是什么作物，处于什么生育期？", "先出现异常的是老叶还是新叶？叶脉和叶缘有什么变化？",
                "近期施肥、灌溉和温度情况如何？是否有土壤检测结果？");
    }

    private Decision unavailable() {
        return new Decision(Status.KNOWLEDGE_UNAVAILABLE, List.of(), List.of(), List.of(),
                List.of("检查知识检索服务后重试"), "知识检索暂不可用，未生成诊断。",
                "EVIDENCE_GUARD", List.of("KNOWLEDGE_SERVICE_UNAVAILABLE"));
    }
}
