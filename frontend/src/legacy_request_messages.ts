// Translate known historical system messages only; saved records and user prose stay intact.
const messages:Record<string,string>={
  "\u8bf7\u9009\u62e9\u7528\u9910\u65b9\u5f0f\uff1a\u5373\u98df\u9910\u98df\u6216\u81ea\u884c\u70f9\u996a\u3002": "Choose a meal arrangement: ready-to-eat or self-catered meals.",
  "\u7528\u9910\u65b9\u5f0f\u540c\u65f6\u5305\u542b\u5373\u98df\u9910\u98df\u548c\u81ea\u884c\u70f9\u996a\uff0c\u8bf7\u660e\u786e\u672c\u6b21\u91c7\u7528\u54ea\u4e00\u79cd\u3002": "Both ready-to-eat and self-catered meals were selected. Choose one arrangement for this trip.",
  "\u8bf7\u586b\u5199\u5f00\u59cb\u65e5\u671f\u3002": "Enter a start date.",
  "\u8bf7\u9009\u62e9\u6f14\u793a\u76ee\u7684\u5730\u3002": "Select a demo destination.",
  "\u76ee\u7684\u5730\u4e0d\u5728\u5f53\u524d synthetic \u6f14\u793a\u8303\u56f4\u5185\uff0c\u8bf7\u9009\u62e9\u652f\u6301\u7684\u5730\u533a\u3002": "Destination is outside the current synthetic demo region. Select a supported region.",
  "\u8bf7\u660e\u786e\u665a\u6570\uff1b\u53ea\u6709\u5929\u6570\u6216\u65e5\u671f\u4e0d\u80fd\u76f4\u63a5\u66ff\u4f60\u786e\u8ba4\u665a\u6570\u3002": "Specify nights. Days or dates alone cannot confirm nights for you.",
  "\u665a\u6570\u8d85\u51fa\u53ef\u8868\u793a\u7684\u65e5\u671f\u8303\u56f4\uff0c\u8bf7\u4fee\u6539\u3002": "Nights exceed the representable date range. Please revise.",
  "\u8bf7\u586b\u5199\u6574\u4e2a\u5c0f\u7ec4\u7684 AUD \u9884\u7b97\u3002": "Enter the whole group AUD budget.",
  "\u8bf7\u5148\u4fdd\u5b58\u5c0f\u7ec4\u4eba\u6570\uff0c\u518d\u91cd\u65b0\u751f\u6210\u6458\u8981\u3002": "Save group size first, then regenerate the summary.",
  "\u201c\u5fc5\u987b\u80fd\u751f\u706b\u201d\u548c\u201c\u4e0d\u751f\u706b\u201d\u5b58\u5728\u51b2\u7a81\uff0c\u8bf7\u9009\u62e9\u672c\u6b21\u884c\u7a0b\u5b9e\u9645\u9700\u8981\u7684\u5b89\u6392\u3002": "Fires required and no campfire conflict. Choose the arrangement needed for this trip."
};
export function englishRequestMessage(message:string):string{
 if(Object.hasOwn(messages,message))return messages[message];
 const nights=message.match(/^(\d+) \u665a\u5e94\u4e3a (\d+) \u5929\uff0c\u8bf7\u4fee\u6539\u51b2\u7a81\u7684\u5929\u6570\u3002$/);
 if(nights)return `${nights[1]} nights should span ${nights[2]} days. Correct the conflicting duration.`;
 const end=message.match(/^\u7ed3\u675f\u65e5\u671f\u5e94\u4e3a (\d{4}-\d{2}-\d{2})\uff0c\u8bf7\u4fee\u6539\u51b2\u7a81\u7684\u65e5\u671f\u3002$/);
 if(end)return `End date should be ${end[1]}. Correct the conflicting date.`;
 const unsupported=message.match(/^\u65e0\u6cd5\u6838\u5b9e\u5fc5\u987b\u6761\u4ef6\u201c([^\n]+)\u201d\u3002\u8bf7\u8bf4\u660e\u5177\u4f53\u9700\u8981\u7684\u8bbe\u65bd\uff0c\u6216\u5c06\u5b83\u8c03\u6574\u4e3a\u504f\u597d\u540e\u91cd\u65b0\u751f\u6210\u6458\u8981\u3002$/);
 if(unsupported)return `Cannot verify required condition: ${unsupported[1]}. Specify the facilities you need, or move it to preferences and regenerate the summary.`;
 return message;
}
