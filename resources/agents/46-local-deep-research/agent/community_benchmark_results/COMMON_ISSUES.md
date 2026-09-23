# Common Benchmarking Issues and Solutions

This guide documents known issues that can affect benchmark results and how to avoid them.

## Model-Related Issues

### 1. Insufficient Context Window
**Problem**: Default context window (4096 tokens) is too small for multi-iteration research.
- **Symptoms**: Model "forgets" earlier search results, produces inconsistent answers
- **Solution**: Increase "Local Provider Context Window Size" to at least 32768 tokens
- **Note**: Each iteration accumulates context from previous searches

### 2. Model Size Limitations
**Problem**: Smaller models may struggle with multi-step reasoning required for research.
- **Symptoms**: Low accuracy, inability to synthesize information across sources
- **Consider**: Larger models for focused-iteration strategy
- **Alternative**: Source-based strategy with fewer iterations may work better for smaller models

### 3. Quantization Impact
**Problem**: Heavy quantization can degrade research performance.
- **Symptoms**: Hallucinations, inability to follow multi-step instructions
- **Recommendation**: Test different quantization levels to find the right balance

## Search Engine Issues

### 1. SearXNG Rate Limiting
**Problem**: Too many requests trigger SearXNG's protective rate limiting.
- **Symptoms**: Empty search results, "No results found" errors
- **Solutions**:
  - Monitor the search health indicator on the benchmark page
  - Reduce questions per iteration
  - Use your own SearXNG instance with appropriate limits
  - Check SearXNG health in Settings → Search Engines before benchmarking
  - Consider alternative search engines for high-volume testing

### 2. Search Provider Limitations
**Problem**: Some search engines provide limited or specialized results.
- **Examples**:
  - Wikipedia-only searches are too narrow for general questions
  - Some providers may have API limits or geographic restrictions
- **Recommendation**: Test with SearXNG (aggregates multiple engines) or Tavily

### 3. Search Engine Configuration
**Problem**: Misconfigured search engines return no results.
- **Check**: API keys are valid and have remaining credits
- **Verify**: Search engine is accessible from your network
- **Test**: Try a manual search through the UI first

## Configuration Issues

### 1. Memory Management
**Problem**: Large models + high context = out of memory errors.
- **Symptoms**: Benchmark crashes, system freezes
- **Solutions**:
  - Monitor RAM/VRAM usage during tests
  - Adjust context window size based on available memory
  - Use quantized models if necessary

### 2. Temperature Settings
**Problem**: Temperature affects consistency of results.
- **For benchmarking**: Lower temperature (0.0-0.1) typically gives more consistent results
- **Document**: Always include temperature in your benchmark submission

### 3. Max Tokens Limit
**Problem**: Low max_tokens cuts off model responses.
- **Symptoms**: Incomplete answers, missing citations
- **Solution**: Ensure max_tokens is sufficient for complete responses

## Strategy-Specific Considerations

### Focused-Iteration Strategy
- **Higher token usage**: More iterations × more questions = more context
- **Context accumulation**: Each iteration adds to the context
- **Time intensive**: Takes longer but may be more thorough
- **Best for**: Models with larger context windows

### Source-Based Strategy
- **Different approach**: Fewer iterations, different search pattern
- **Efficiency**: Generally faster than focused-iteration
- **Consider for**: Models with limited context windows

## Benchmarking Best Practices

### 1. Start Small
- Begin with 10-20 questions to verify configuration
- Check that search results are being retrieved
- Monitor resource usage before scaling up

### 2. Consistent Testing
- Use the same search configuration across tests
- Document the exact settings used
- Note any errors or anomalies

### 3. Fair Comparisons
- Test both strategies when possible
- The benchmarking tool automatically selects questions from benchmarks (e.g. SimpleQA) for consistency
- Include all relevant configuration details in your submission

### 4. Resource Monitoring
```bash
# Monitor GPU usage (if using NVIDIA)
nvidia-smi -l 1

# Monitor system resources
htop

# Check Ollama models loaded
ollama list
```

## Interpreting Results

### What Affects Accuracy
- Model size and architecture
- Quantization level
- Context window size
- Search result quality
- Strategy choice
- Temperature and other parameters

### Red Flags in Results
- **Extremely fast completion**: May indicate search or processing issues
- **No search results**: Check search engine configuration
- **Consistent errors**: Look for configuration problems

## Getting Help

If you encounter issues:
1. Check the [FAQ](https://github.com/LearningCircuit/local-deep-research/blob/main/docs/faq.md)
2. Search existing [GitHub Issues](https://github.com/LearningCircuit/local-deep-research/issues)
3. Join our [Discord](https://discord.gg/ttcqQeFcJ3) for community help
4. Include error messages, configuration details, and logs when asking for help
