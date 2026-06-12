// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { removeStringFromText } from './dataset-file-utils';

describe('removeStringFromText', () => {
  const exampleText = `{"id":"5728170d3acd2414000df444","answers":{"text":["over 2,000","2,000 buildings","over 2,"],"answer_start":[271,276,271]},"prompt":"Extract from the following context the minimal span word for word that best answers the question.\\n- If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct.\\n- If you don't know the answer to a question, please don't share false information.\\n- If the answer is not in the context, the answer should be \\"?\\".\\n- Your answer should not include any other text than the answer to the question. Don't include any other text like \\"Here is the answer to the question:\\" or \\"The minimal span word for word that best answers the question is:\\" or anything like that.\\n\\nContext: On May 3, 1901, downtown Jacksonville was ravaged by a fire that started as a kitchen fire. Spanish moss at a nearby mattress factory was quickly engulfed in flames and enabling the fire to spread rapidly. In just eight hours, it swept through 146 city blocks, destroyed over 2,000 buildings, left about 10,000 homeless and killed 7 residents. The Confederate Monument in Hemming Park was one of the only landmarks to survive the fire. Governor Jennings declare martial law and sent the state militia to maintain order. On May 17 municipal authority resumed in Jacksonville. It is said the glow from the flames could be seen in Savannah, Georgia, and the smoke plumes seen in Raleigh, North Carolina. Known as the \\"Great Fire of 1901\\", it was one of the worst disasters in Florida history and the largest urban fire in the southeastern United States. Architect Henry John Klutho was a primary figure in the reconstruction of the city. The first multi-story structure built by Klutho was the Dyal-Upchurch Building in 1902. The St. James Building, built on the previous site of the St. James Hotel that burned down, was built in 1912 as Klutho's crowning achievement.\\nQuestion: How many buildings were razed by the Jacksonville fire? Answer:","ideal_response":"over 2,000"}
{"id":"5726e680dd62a815002e946f","answers":{"text":["between 1859 and 1865","1859 and 1865","between 1859 and 1865"],"answer_start":[79,87,79]},"prompt":"Extract from the following context the minimal span word for word that best answers the question.\\n- If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct.\\n- If you don't know the answer to a question, please don't share false information.\\n- If the answer is not in the context, the answer should be \\"?\\".\\n- Your answer should not include any other text than the answer to the question. Don't include any other text like \\"Here is the answer to the question:\\" or \\"The minimal span word for word that best answers the question is:\\" or anything like that.\\n\\nContext: The Soulages collection of Italian and French Renaissance objects was acquired between 1859 and 1865, and includes several cassone. The John Jones Collection of French 18th-century art and furnishings was left to the museum in 1882, then valued at £250,000. One of the most important pieces in this collection is a marquetry commode by the ébéniste Jean Henri Riesener dated c1780. Other signed pieces of furniture in the collection include a bureau by Jean-François Oeben, a pair of pedestals with inlaid brass work by André Charles Boulle, a commode by Bernard Vanrisamburgh and a work-table by Martin Carlin. Other 18th-century ébénistes represented in the Museum collection include Adam Weisweiler, David Roentgen, Gilles Joubert & Pierre Langlois. In 1901, Sir George Donaldson donated several pieces of art Nouveau furniture to the museum, which he had acquired the previous year at the Paris Exposition Universelle. This was criticized at the time, with the result that the museum ceased to collect contemporary items and did not do so again until the 1960s. In 1986 the Lady Abingdon collection of French Empire furniture was bequeathed by Mrs T. R. P. Hole.\\nQuestion: When was the Soulages collection acquired? Answer:","ideal_response":"between 1859 and 1865"}`;

  const textToRemove = `Extract from the following context the minimal span word for word that best answers the question.\\n- If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct.\\n- If you don't know the answer to a question, please don't share false information.\\n- If the answer is not in the context, the answer should be \\"?\\".\\n- Your answer should not include any other text than the answer to the question. Don't include any other text like \\"Here is the answer to the question:\\" or \\"The minimal span word for word that best answers the question is:\\" or anything like that.\\n\\n`;

  const expectedResult = `{"id":"5728170d3acd2414000df444","answers":{"text":["over 2,000","2,000 buildings","over 2,"],"answer_start":[271,276,271]},"prompt":"Context: On May 3, 1901, downtown Jacksonville was ravaged by a fire that started as a kitchen fire. Spanish moss at a nearby mattress factory was quickly engulfed in flames and enabling the fire to spread rapidly. In just eight hours, it swept through 146 city blocks, destroyed over 2,000 buildings, left about 10,000 homeless and killed 7 residents. The Confederate Monument in Hemming Park was one of the only landmarks to survive the fire. Governor Jennings declare martial law and sent the state militia to maintain order. On May 17 municipal authority resumed in Jacksonville. It is said the glow from the flames could be seen in Savannah, Georgia, and the smoke plumes seen in Raleigh, North Carolina. Known as the \\"Great Fire of 1901\\", it was one of the worst disasters in Florida history and the largest urban fire in the southeastern United States. Architect Henry John Klutho was a primary figure in the reconstruction of the city. The first multi-story structure built by Klutho was the Dyal-Upchurch Building in 1902. The St. James Building, built on the previous site of the St. James Hotel that burned down, was built in 1912 as Klutho's crowning achievement.\\nQuestion: How many buildings were razed by the Jacksonville fire? Answer:","ideal_response":"over 2,000"}
{"id":"5726e680dd62a815002e946f","answers":{"text":["between 1859 and 1865","1859 and 1865","between 1859 and 1865"],"answer_start":[79,87,79]},"prompt":"Context: The Soulages collection of Italian and French Renaissance objects was acquired between 1859 and 1865, and includes several cassone. The John Jones Collection of French 18th-century art and furnishings was left to the museum in 1882, then valued at £250,000. One of the most important pieces in this collection is a marquetry commode by the ébéniste Jean Henri Riesener dated c1780. Other signed pieces of furniture in the collection include a bureau by Jean-François Oeben, a pair of pedestals with inlaid brass work by André Charles Boulle, a commode by Bernard Vanrisamburgh and a work-table by Martin Carlin. Other 18th-century ébénistes represented in the Museum collection include Adam Weisweiler, David Roentgen, Gilles Joubert & Pierre Langlois. In 1901, Sir George Donaldson donated several pieces of art Nouveau furniture to the museum, which he had acquired the previous year at the Paris Exposition Universelle. This was criticized at the time, with the result that the museum ceased to collect contemporary items and did not do so again until the 1960s. In 1986 the Lady Abingdon collection of French Empire furniture was bequeathed by Mrs T. R. P. Hole.\\nQuestion: When was the Soulages collection acquired? Answer:","ideal_response":"between 1859 and 1865"}`;

  it('should remove the specified text from the input', () => {
    const result = removeStringFromText(exampleText, textToRemove);
    expect(result).toBe(expectedResult);
  });

  it('should handle empty input text', () => {
    const result = removeStringFromText('', textToRemove);
    expect(result).toBe('');
  });

  it('should handle empty string to remove', () => {
    const result = removeStringFromText(exampleText, '');
    expect(result).toBe(exampleText);
  });

  it('should handle text that does not contain the string to remove', () => {
    const result = removeStringFromText(exampleText, 'nonexistent text');
    expect(result).toBe(exampleText);
  });

  it('should handle multiple occurrences of the string to remove', () => {
    const text = 'hello hello hello';
    const result = removeStringFromText(text, 'hello');
    expect(result).toBe('  ');
  });

  it('should handle special characters in the string to remove', () => {
    const text = 'hello\nworld\nhello\nworld';
    const result = removeStringFromText(text, 'hello\nworld');
    expect(result).toBe('\n');
  });

  it('should handle JSON string values with escaped characters', () => {
    const text = '{"text": "hello\\nworld"}';
    const result = removeStringFromText(text, 'hello\\nworld');
    expect(result).toBe('{"text": ""}');
  });
});
