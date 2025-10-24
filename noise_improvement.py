import seaborn as sns
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

noise_type_data = 2*['None','Signal','Kinetic']
enriched_data = 3*["Baseline"] + 3*["Baseline + Block"]
mae = [0.1681,0.7248,0.6072,0.09016,0.2524,0.3989]

df = pd.DataFrame(data={'Noise Type': noise_type_data, 'Training Dataset Composition': enriched_data, 'Test MAE': mae})

#Make grouped barplot
catplot = sns.catplot(df,x="Training Dataset Composition",y="Test MAE",hue="Noise Type",kind="bar",legend=False)
catplot.figure.set_figheight(6)
catplot.figure.set_figwidth(6)
plt.ylabel("Test MAE", fontsize=25)
plt.xlabel("Training Dataset",fontsize=25)
plt.xticks(fontsize=17)
plt.yticks(fontsize=17)

#Create legend
none_patch = Patch(color="tab:blue", label="None")
signal_patch = Patch(color="tab:orange", label="Signal")
kinetic_patch = Patch(color='tab:green', label="Kinetic")
plt.legend(handles=[none_patch,signal_patch,kinetic_patch], title='Noise Type',title_fontsize=15,fontsize=15)
plt.tight_layout()
plt.savefig("noise_improvement.png", dpi=600)